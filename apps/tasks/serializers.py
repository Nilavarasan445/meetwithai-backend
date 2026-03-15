from rest_framework import serializers
from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    meeting_title = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id", "meeting", "meeting_title", "title", "description",
            "assigned_to", "due_date", "estimated_minutes", "status",
            "created_at", "updated_at", "facility",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "meeting_title"]

    def get_meeting_title(self, obj):
        return obj.meeting.title if obj.meeting else None


class TaskCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["meeting", "title", "description", "assigned_to", "due_date", "estimated_minutes", "status", "facility"]

    def validate_facility(self, value):
        request = self.context.get("request")
        if value and (value.owner != request.user and not value.members.filter(id=request.user.id).exists()):
            raise serializers.ValidationError("Facility not found or access denied.")
        return value

    def validate_meeting(self, value):
        request = self.context.get("request")
        if value and value.user != request.user:
            raise serializers.ValidationError("Meeting not found.")
        return value
