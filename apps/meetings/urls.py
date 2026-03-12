from django.urls import path
from . import views

urlpatterns = [
    path("", views.MeetingListCreateView.as_view(), name="meeting-list-create"),
    path("<int:pk>/", views.MeetingDetailView.as_view(), name="meeting-detail"),
    path("<int:pk>/transcript/", views.meeting_transcript, name="meeting-transcript"),
    path("<int:pk>/analyze/", views.analyze_meeting, name="meeting-analyze"),
    path("<int:pk>/status/", views.meeting_status, name="meeting-status"),
]
