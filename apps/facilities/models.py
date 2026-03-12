from django.db import models
from django.conf import settings


class Facility(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_facilities",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="facilities",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facilities"
        ordering = ["-created_at"]
        verbose_name_plural = "Facilities"

    def __str__(self):
        return self.name
