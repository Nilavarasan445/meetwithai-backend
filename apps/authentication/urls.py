from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("token/refresh/", views.token_refresh, name="token_refresh"),
    path("profile/", views.profile, name="profile"),
    # GitHub OAuth
    path("github/url/", views.github_auth_url, name="github-auth-url"),
    path("github/callback/", views.github_callback, name="github-callback"),
    path("github/status/", views.github_status, name="github-status"),
    path("github/disconnect/", views.github_disconnect, name="github-disconnect"),
]
