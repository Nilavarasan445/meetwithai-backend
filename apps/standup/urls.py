from django.urls import path
from . import views

urlpatterns = [
    # Standup
    path("generate/", views.generate_standup, name="standup-generate"),
    path("", views.standup_list, name="standup-list"),
    path("<int:pk>/", views.standup_detail, name="standup-detail"),
    path("commits/", views.github_commits, name="github-commits"),
    # Daily Report
    path("report/generate/", views.generate_daily_report, name="report-generate"),
    path("report/", views.daily_report_list, name="report-list"),
    path("report/<int:pk>/", views.daily_report_detail, name="report-detail"),
]
