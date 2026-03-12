from django.db import models
from django.conf import settings


class OAuthToken(models.Model):
    PROVIDER_GOOGLE = "google"
    PROVIDER_MICROSOFT = "microsoft"
    PROVIDER_CHOICES = [
        (PROVIDER_GOOGLE, "Google"),
        (PROVIDER_MICROSOFT, "Microsoft"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="oauth_tokens",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    email = models.EmailField(blank=True)  # connected account email
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "oauth_tokens"
        unique_together = [("user", "provider")]

    def __str__(self):
        return f"{self.user.email} - {self.provider}"

    @property
    def is_expired(self):
        if not self.token_expiry:
            return False
        from django.utils import timezone
        return timezone.now() >= self.token_expiry
