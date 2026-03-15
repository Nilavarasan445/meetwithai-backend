from django.db import models
from django.conf import settings


class DailyReport(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_reports",
    )
    date = models.DateField()
    # Raw activity data stored as JSON
    commits = models.JSONField(default=list)
    pull_requests = models.JSONField(default=list)
    tasks_completed = models.JSONField(default=list)
    tasks_in_progress = models.JSONField(default=list)
    meetings = models.JSONField(default=list)
    notes_count = models.PositiveIntegerField(default=0)
    # Timeline — list of {time, type, title} dicts sorted by time
    timeline = models.JSONField(default=list)
    # AI summary
    ai_summary = models.TextField(blank=True)
    # Stats
    total_commits = models.PositiveIntegerField(default=0)
    total_prs = models.PositiveIntegerField(default=0)
    total_tasks_done = models.PositiveIntegerField(default=0)
    total_meetings = models.PositiveIntegerField(default=0)
    total_meeting_minutes = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_reports"
        ordering = ["-date"]
        unique_together = [["user", "date"]]

    def __str__(self):
        return f"Report {self.date} — {self.user.email}"


class Standup(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="standups",
    )
    date = models.DateField()
    content = models.TextField()

    # Source data snapshot
    commits_summary = models.TextField(blank=True)
    tasks_summary = models.TextField(blank=True)
    meetings_summary = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "standups"
        ordering = ["-date", "-created_at"]
        unique_together = [["user", "date"]]

    def __str__(self):
        return f"Standup {self.date} — {self.user.email}"
