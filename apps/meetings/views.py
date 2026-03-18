from rest_framework import status, generics, filters
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Meeting, Transcript
from .serializers import (
    MeetingListSerializer,
    MeetingDetailSerializer,
    MeetingUploadSerializer,
    TranscriptSerializer,
)
from .tasks import process_meeting
from django.conf import settings

class MeetingListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    filterset_fields = ["status", "facility"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = Meeting.objects.filter(user=self.request.user).prefetch_related(
            "summary", "decisions", "tasks"
        )
        facility_id = self.request.query_params.get("facility")
        if facility_id:
            queryset = queryset.filter(facility_id=facility_id)
        return queryset

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MeetingUploadSerializer
        return MeetingListSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if not user.can_upload_meeting():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Free plan limit reached (5 meetings/month). Upgrade to Pro."
            )
        # If no facility provided, assign to user's first facility
        data = serializer.validated_data
        if not data.get('facility'):
            from apps.facilities.models import Facility
            first_facility = Facility.objects.filter(owner=user).first()
            if first_facility:
                data['facility'] = first_facility
        meeting = serializer.save(user=user, status=Meeting.STATUS_PENDING)
        # Trigger background processing — gracefully handle missing broker
        try:
            process_meeting.delay(meeting.id)
        except Exception as e:
            # No broker available — run the underlying function directly
            # Import the raw function (not the Celery task wrapper)
            from apps.meetings.tasks import process_meeting as _task
            try:
                _task.run(meeting.id)  # call .run() to bypass Celery machinery
            except AttributeError:
                # Fallback: call underlying function directly via apply()
                _task.apply(args=[meeting.id])
        return meeting

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = self.perform_create(serializer)
        return Response(
            MeetingDetailSerializer(meeting).data,
            status=status.HTTP_201_CREATED,
        )


class MeetingDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Meeting.objects.filter(user=self.request.user).prefetch_related(
            "summary", "transcript", "decisions", "tasks"
        )

    def get_serializer_class(self):
        return MeetingDetailSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meeting_transcript(request, pk):
    try:
        meeting = Meeting.objects.get(pk=pk, user=request.user)
    except Meeting.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        transcript = meeting.transcript
        return Response(TranscriptSerializer(transcript).data)
    except Transcript.DoesNotExist:
        return Response(
            {"detail": "Transcript not ready yet."},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_meeting(request, pk):
    """Re-trigger AI analysis for an existing meeting."""
    try:
        meeting = Meeting.objects.get(pk=pk, user=request.user)
    except Meeting.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if meeting.status in [Meeting.STATUS_TRANSCRIBING, Meeting.STATUS_ANALYZING]:
        return Response({"detail": "Analysis already in progress."})

    meeting.status = Meeting.STATUS_PENDING
    meeting.save(update_fields=["status"])
    try:
        process_meeting.delay(meeting.id)
    except Exception:
        process_meeting(meeting.id)

    return Response({"detail": "Analysis queued.", "meeting_id": meeting.id})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meeting_status(request, pk):
    """Polling endpoint for frontend to check processing status."""
    try:
        meeting = Meeting.objects.get(pk=pk, user=request.user)
    except Meeting.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        "id": meeting.id,
        "status": meeting.status,
        "error_message": meeting.error_message,
    })
