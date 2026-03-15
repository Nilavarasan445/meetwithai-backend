from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/meetings/", include("apps.meetings.urls")),
    path("api/tasks/", include("apps.tasks.urls")),
    path("api/facilities/", include("apps.facilities.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
    path("api/standup/", include("apps.standup.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
