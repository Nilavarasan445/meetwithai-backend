from rest_framework import serializers
from .models import Meeting, Transcript, MeetingSummary, MeetingDecision
from apps.tasks.models import Task


class MeetingDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingDecision
        fields = ["id", "decision_text", "order"]


class MeetingSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingSummary
        fields = ["summary_text", "next_steps", "created_at"]


class TranscriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcript
        fields = ["text", "word_count", "created_at"]


class TaskInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["id", "title", "assigned_to", "due_date", "status"]


class MeetingListSerializer(serializers.ModelSerializer):
    summary_text = serializers.SerializerMethodField()
    task_count = serializers.SerializerMethodField()
    decision_count = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            "id", "title", "status", "duration_display",
            "created_at", "summary_text", "task_count", "decision_count",
            "facility",
        ]

    def get_summary_text(self, obj):
        if hasattr(obj, "summary"):
            return obj.summary.summary_text
        return None

    def get_task_count(self, obj):
        return obj.tasks.count()

    def get_decision_count(self, obj):
        return obj.decisions.count()


class MeetingDetailSerializer(serializers.ModelSerializer):
    summary = MeetingSummarySerializer(read_only=True)
    transcript = TranscriptSerializer(read_only=True)
    decisions = MeetingDecisionSerializer(many=True, read_only=True)
    tasks = TaskInlineSerializer(many=True, read_only=True)
    duration_display = serializers.ReadOnlyField()

    class Meta:
        model = Meeting
        fields = [
            "id", "title", "status", "recording_file",
            "duration_display", "duration_seconds",
            "created_at", "updated_at", "error_message",
            "summary", "transcript", "decisions", "tasks",
            "facility",
        ]


class MeetingUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ["title", "recording_file", "facility"]

    def validate_recording_file(self, value):
        allowed = [".mp3", ".mp4", ".wav", ".m4a", ".webm"]
        import os
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in allowed:
            raise serializers.ValidationError(
                f"Unsupported file type. Allowed: {', '.join(allowed)}"
            )
        max_size = 500 * 1024 * 1024  # 500MB
        if value.size > max_size:
            raise serializers.ValidationError("File too large. Max 500MB.")
        return value
