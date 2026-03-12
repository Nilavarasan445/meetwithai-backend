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
        meeting = serializer.save(user=user, status=Meeting.STATUS_PENDING)
        # Trigger background processing
        process_meeting.delay(meeting.id)
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
    process_meeting.delay(meeting.id)

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
