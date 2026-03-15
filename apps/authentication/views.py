import requests
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import RegisterSerializer, LoginSerializer, UserProfileSerializer


def get_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        return Response(
            {"user": UserProfileSerializer(user).data, "tokens": get_tokens(user)},
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data["user"]
        return Response({"user": UserProfileSerializer(user).data, "tokens": get_tokens(user)})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def token_refresh(request):
    from rest_framework_simplejwt.views import TokenRefreshView
    return TokenRefreshView.as_view()(request._request)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def profile(request):
    if request.method == "GET":
        return Response(UserProfileSerializer(request.user).data)
    serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"detail": "Successfully logged out."})
    except Exception:
        return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)


# ── GitHub OAuth ──────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_auth_url(request):
    """Return the GitHub OAuth URL for the frontend to redirect to."""
    client_id = settings.GITHUB_CLIENT_ID
    redirect_uri = settings.GITHUB_REDIRECT_URI
    scope = "read:user user:email repo"
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
    )
    return Response({"url": url})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def github_callback(request):
    """Exchange code for GitHub access token and store on user."""
    code = request.data.get("code")
    if not code:
        return Response({"detail": "code is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Exchange code for token
    resp = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
        },
        timeout=15,
    )

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        return Response(
            {"detail": data.get("error_description", "Failed to get GitHub token.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Fetch GitHub user info
    gh_resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=15,
    )
    gh_user = gh_resp.json()

    request.user.github_access_token = access_token
    request.user.github_username = gh_user.get("login", "")
    request.user.save(update_fields=["github_access_token", "github_username"])

    return Response({
        "connected": True,
        "github_username": request.user.github_username,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_status(request):
    """Return whether GitHub is connected for this user."""
    connected = bool(request.user.github_access_token)
    return Response({
        "connected": connected,
        "github_username": request.user.github_username if connected else None,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def github_disconnect(request):
    """Disconnect GitHub from the user account."""
    request.user.github_access_token = None
    request.user.github_username = None
    request.user.save(update_fields=["github_access_token", "github_username"])
    return Response({"connected": False})
