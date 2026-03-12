from django.db import models
from django.conf import settings


class Meeting(models.Model):
    STATUS_PENDING = "pending"
    STATUS_TRANSCRIBING = "transcribing"
    STATUS_ANALYZING = "analyzing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_TRANSCRIBING, "Transcribing"),
        (STATUS_ANALYZING, "Analyzing"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="meetings",
    )
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        related_name="meetings",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    recording_file = models.FileField(upload_to="recordings/%Y/%m/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "meetings"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user.email})"

    @property
    def duration_display(self):
        if not self.duration_seconds:
            return None
        m, s = divmod(self.duration_seconds, 60)
        return f"{m}m {s}s"


class Transcript(models.Model):
    meeting = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, related_name="transcript"
    )
    text = models.TextField()
    word_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transcripts"

    def save(self, *args, **kwargs):
        self.word_count = len(self.text.split())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Transcript for {self.meeting.title}"


class MeetingSummary(models.Model):
    meeting = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, related_name="summary"
    )
    summary_text = models.TextField()
    next_steps = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meeting_summaries"

    def __str__(self):
        return f"Summary for {self.meeting.title}"


class MeetingDecision(models.Model):
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="decisions"
    )
    decision_text = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meeting_decisions"
        ordering = ["order"]

    def __str__(self):
        return f"Decision: {self.decision_text[:60]}"
