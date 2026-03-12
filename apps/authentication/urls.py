from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("token/refresh/", views.token_refresh, name="token_refresh"),
    path("profile/", views.profile, name="profile"),
]
