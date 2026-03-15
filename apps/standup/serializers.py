from rest_framework import serializers
from .models import Standup, DailyReport


class StandupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Standup
        fields = [
            "id", "date", "content",
            "commits_summary", "tasks_summary", "meetings_summary",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = [
            "id", "date",
            "commits", "pull_requests",
            "tasks_completed", "tasks_in_progress",
            "meetings", "notes_count",
            "timeline", "ai_summary",
            "total_commits", "total_prs",
            "total_tasks_done", "total_meetings", "total_meeting_minutes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
