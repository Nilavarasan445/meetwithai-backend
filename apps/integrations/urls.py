from django.urls import path
from . import views

urlpatterns = [
    # Status
    path("status/", views.integration_status, name="integration-status"),
    path("<str:provider>/disconnect/", views.disconnect_integration, name="integration-disconnect"),

    # Google
    path("google/auth-url/", views.google_auth_url, name="google-auth-url"),
    path("google/callback/", views.google_callback, name="google-callback"),
    path("google/recordings/", views.google_recordings, name="google-recordings"),
    path("google/import/", views.import_google_recording, name="google-import"),

    # Microsoft
    path("microsoft/auth-url/", views.microsoft_auth_url, name="microsoft-auth-url"),
    path("microsoft/callback/", views.microsoft_callback, name="microsoft-callback"),
    path("microsoft/recordings/", views.microsoft_recordings, name="microsoft-recordings"),
    path("microsoft/import/", views.import_microsoft_recording, name="microsoft-import"),
    # Combined
    path("calendar/events/", views.calendar_events, name="calendar-events"),
]
