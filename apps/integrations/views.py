import logging
import os
import requests
import tempfile
from urllib.parse import urlencode
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import OAuthToken
from apps.meetings.models import Meeting
from apps.meetings.tasks import process_meeting

logger = logging.getLogger(__name__)

# ─── Google OAuth ────────────────────────────────────────────────────────────

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# ─── Microsoft OAuth ─────────────────────────────────────────────────────────

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_URL = "https://graph.microsoft.com/v1.0"

MS_SCOPES = [
    "User.Read",
    "Files.Read",
    "Calendars.Read",
    "OnlineMeetings.Read",
    "offline_access",
]


# ─── Status endpoints ─────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def integration_status(request):
    """Return which providers are connected for the current user."""
    connected = {}
    for token in OAuthToken.objects.filter(user=request.user):
        connected[token.provider] = {
            "connected": True,
            "email": token.email,
        }
    return Response({
        "google": connected.get("google", {"connected": False}),
        "microsoft": connected.get("microsoft", {"connected": False}),
    })


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def disconnect_integration(request, provider):
    """Disconnect a provider."""
    deleted, _ = OAuthToken.objects.filter(user=request.user, provider=provider).delete()
    if deleted:
        return Response({"detail": f"{provider} disconnected."})
    return Response({"detail": "Not connected."}, status=404)


# ─── Google ───────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_auth_url(request):
    """Return the Google OAuth URL for the frontend to redirect to."""
    client_id = settings.GOOGLE_CLIENT_ID
    redirect_uri = settings.GOOGLE_REDIRECT_URI

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": str(request.user.id),  # simple CSRF-like state
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return Response({"url": url})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def google_callback(request):
    """Exchange auth code for tokens and save them."""
    code = request.data.get("code")
    if not code:
        return Response({"detail": "Missing code."}, status=400)

    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    token_resp = requests.post(GOOGLE_TOKEN_URL, data=data)
    if not token_resp.ok:
        logger.error(f"Google token exchange failed: {token_resp.text}")
        return Response({"detail": "Token exchange failed."}, status=400)

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    expiry = timezone.now() + timedelta(seconds=expires_in)

    # Get user email
    info_resp = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    email = info_resp.json().get("email", "") if info_resp.ok else ""

    OAuthToken.objects.update_or_create(
        user=request.user,
        provider=OAuthToken.PROVIDER_GOOGLE,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": expiry,
            "email": email,
        },
    )
    return Response({"detail": "Google connected.", "email": email})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def google_recordings(request):
    """List Google Meet recordings from Google Drive."""
    try:
        token = OAuthToken.objects.get(user=request.user, provider=OAuthToken.PROVIDER_GOOGLE)
    except OAuthToken.DoesNotExist:
        return Response({"detail": "Google not connected."}, status=400)

    access_token = _refresh_google_token_if_needed(token)

    params = {
        "q": "mimeType='video/mp4' and name contains 'Meet'",
        "fields": "files(id,name,size,createdTime,webViewLink)",
        "orderBy": "createdTime desc",
        "pageSize": 20,
    }
    resp = requests.get(
        GOOGLE_DRIVE_FILES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )

    if not resp.ok:
        # Try broader search if Meet-specific fails
        params["q"] = "mimeType='video/mp4'"
        resp = requests.get(
            GOOGLE_DRIVE_FILES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )

    if not resp.ok:
        return Response({"detail": "Failed to fetch recordings."}, status=400)

    files = resp.json().get("files", [])
    return Response({"recordings": files})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_google_recording(request):
    """Download a Google Drive file and create a Meeting from it."""
    file_id = request.data.get("file_id")
    file_name = request.data.get("file_name", "Google Meet Recording")
    title = request.data.get("title", file_name)

    if not file_id:
        return Response({"detail": "file_id required."}, status=400)

    try:
        token = OAuthToken.objects.get(user=request.user, provider=OAuthToken.PROVIDER_GOOGLE)
    except OAuthToken.DoesNotExist:
        return Response({"detail": "Google not connected."}, status=400)

    if not request.user.can_upload_meeting():
        return Response({"detail": "Free plan limit reached (5 meetings/month)."}, status=403)

    access_token = _refresh_google_token_if_needed(token)

    # Download file from Drive
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    file_resp = requests.get(
        download_url,
        headers={"Authorization": f"Bearer {access_token}"},
        stream=True,
    )

    if not file_resp.ok:
        return Response({"detail": "Failed to download recording."}, status=400)

    # Save to temp file then to Meeting
    suffix = ".mp4" if "mp4" in file_name else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in file_resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        from django.core.files import File as DjangoFile
        facility_id = request.data.get("facility")
        meeting = Meeting.objects.create(
            user=request.user,
            facility_id=facility_id,
            title=title,
            status=Meeting.STATUS_PENDING,
        )
        with open(tmp_path, "rb") as f:
            safe_name = title.replace(" ", "_")[:50] + suffix
            meeting.recording_file.save(safe_name, DjangoFile(f), save=True)

        process_meeting.delay(meeting.id)
        return Response({"meeting_id": meeting.id, "detail": "Import started."}, status=201)
    finally:
        os.unlink(tmp_path)


# ─── Microsoft ────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def microsoft_auth_url(request):
    """Return the Microsoft OAuth URL."""
    client_id = settings.MICROSOFT_CLIENT_ID
    redirect_uri = settings.MICROSOFT_REDIRECT_URI

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(MS_SCOPES),
        "response_mode": "query",
        "state": str(request.user.id),
    }
    url = f"{MS_AUTH_URL}?{urlencode(params)}"
    return Response({"url": url})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def microsoft_callback(request):
    """Exchange auth code for Microsoft tokens."""
    code = request.data.get("code")
    if not code:
        return Response({"detail": "Missing code."}, status=400)

    data = {
        "code": code,
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    token_resp = requests.post(MS_TOKEN_URL, data=data)
    if not token_resp.ok:
        logger.error(f"Microsoft token exchange failed: {token_resp.text}")
        return Response({"detail": "Token exchange failed."}, status=400)

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    expiry = timezone.now() + timedelta(seconds=expires_in)

    # Get user profile
    profile_resp = requests.get(
        f"{MS_GRAPH_URL}/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    email = profile_resp.json().get("mail") or profile_resp.json().get("userPrincipalName", "") if profile_resp.ok else ""

    OAuthToken.objects.update_or_create(
        user=request.user,
        provider=OAuthToken.PROVIDER_MICROSOFT,
        defaults={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": expiry,
            "email": email,
        },
    )
    return Response({"detail": "Microsoft connected.", "email": email})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def microsoft_recordings(request):
    """List Teams meeting recordings from OneDrive/SharePoint."""
    try:
        token = OAuthToken.objects.get(user=request.user, provider=OAuthToken.PROVIDER_MICROSOFT)
    except OAuthToken.DoesNotExist:
        return Response({"detail": "Microsoft not connected."}, status=400)

    access_token = _refresh_microsoft_token_if_needed(token)

    # Search OneDrive for Teams recordings
    resp = requests.get(
        f"{MS_GRAPH_URL}/me/drive/root/search(q='Teams Meeting Recording')?$select=id,name,size,createdDateTime,webUrl",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if not resp.ok:
        # Fallback: list root drive items
        resp = requests.get(
            f"{MS_GRAPH_URL}/me/drive/root/children?$select=id,name,size,createdDateTime,webUrl&$filter=file ne null",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if not resp.ok:
        return Response({"detail": "Failed to fetch recordings."}, status=400)

    items = resp.json().get("value", [])
    recordings = [
        {
            "id": item["id"],
            "name": item["name"],
            "size": item.get("size"),
            "createdTime": item.get("createdDateTime"),
            "webViewLink": item.get("webUrl"),
        }
        for item in items
        if item.get("name", "").endswith((".mp4", ".mp3", ".wav"))
    ]
    return Response({"recordings": recordings})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_microsoft_recording(request):
    """Download a OneDrive file and create a Meeting from it."""
    file_id = request.data.get("file_id")
    file_name = request.data.get("file_name", "Teams Recording")
    title = request.data.get("title", file_name)

    if not file_id:
        return Response({"detail": "file_id required."}, status=400)

    try:
        token = OAuthToken.objects.get(user=request.user, provider=OAuthToken.PROVIDER_MICROSOFT)
    except OAuthToken.DoesNotExist:
        return Response({"detail": "Microsoft not connected."}, status=400)

    if not request.user.can_upload_meeting():
        return Response({"detail": "Free plan limit reached (5 meetings/month)."}, status=403)

    access_token = _refresh_microsoft_token_if_needed(token)

    # Get download URL
    meta_resp = requests.get(
        f"{MS_GRAPH_URL}/me/drive/items/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not meta_resp.ok:
        return Response({"detail": "Failed to get file metadata."}, status=400)

    download_url = meta_resp.json().get("@microsoft.graph.downloadUrl")
    if not download_url:
        return Response({"detail": "No download URL available."}, status=400)

    file_resp = requests.get(download_url, stream=True)
    if not file_resp.ok:
        return Response({"detail": "Failed to download recording."}, status=400)

    suffix = ".mp4" if "mp4" in file_name else ".mp3"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in file_resp.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        from django.core.files import File as DjangoFile
        facility_id = request.data.get("facility")
        meeting = Meeting.objects.create(
            user=request.user,
            facility_id=facility_id,
            title=title,
            status=Meeting.STATUS_PENDING,
        )
        with open(tmp_path, "rb") as f:
            safe_name = title.replace(" ", "_")[:50] + suffix
            meeting.recording_file.save(safe_name, DjangoFile(f), save=True)

        process_meeting.delay(meeting.id)
        return Response({"meeting_id": meeting.id, "detail": "Import started."}, status=201)
    finally:
        os.unlink(tmp_path)


# ─── Token helpers ────────────────────────────────────────────────────────────

def _refresh_google_token_if_needed(token: OAuthToken) -> str:
    if not token.is_expired:
        return token.access_token

    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": token.refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(GOOGLE_TOKEN_URL, data=data)
    if resp.ok:
        new_tokens = resp.json()
        token.access_token = new_tokens["access_token"]
        token.token_expiry = timezone.now() + timedelta(seconds=new_tokens.get("expires_in", 3600))
        token.save(update_fields=["access_token", "token_expiry"])
    return token.access_token


def _refresh_microsoft_token_if_needed(token: OAuthToken) -> str:
    if not token.is_expired:
        return token.access_token

    data = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "refresh_token": token.refresh_token,
        "grant_type": "refresh_token",
        "scope": " ".join(MS_SCOPES),
    }
    resp = requests.post(MS_TOKEN_URL, data=data)
    if resp.ok:
        new_tokens = resp.json()
        token.access_token = new_tokens["access_token"]
        token.refresh_token = new_tokens.get("refresh_token", token.refresh_token)
        token.token_expiry = timezone.now() + timedelta(seconds=new_tokens.get("expires_in", 3600))
        token.save(update_fields=["access_token", "refresh_token", "token_expiry"])
    return token.access_token


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calendar_events(request):
    """Fetch calendar events from all connected providers."""
    events = []
    
    # ─── Google ────────────────────────────────────────────────────────────
    try:
        google_token = OAuthToken.objects.get(user=request.user, provider=OAuthToken.PROVIDER_GOOGLE)
        google_access_token = _refresh_google_token_if_needed(google_token)
        now = timezone.now()

        time_min = (now - timedelta(days=30)).astimezone(timezone.utc).isoformat()

        params = {
            "timeMin": time_min,
            "singleEvents": True,
            "orderBy": "startTime",
            "timeZone": "Asia/Kolkata",
        }
        resp = requests.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {google_access_token}"},
            params=params,
        )
        if resp.ok:
            items = resp.json().get("items", [])
            for item in items:
                events.append({
                    "id": f"google_{item.get('id')}",
                    "title": item.get("summary", "No Title"),
                    "start": item.get("start", {}).get("dateTime") or item.get("start", {}).get("date"),
                    "end": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date"),
                    "meeting_url": item.get("hangoutLink"),
                    "html_link": item.get("htmlLink"),
                    "provider": "google",
                })
        else:
            logger.error(f"Google Calendar fetch failed: {resp.text}")
    except OAuthToken.DoesNotExist:
        pass

    # ─── Microsoft ─────────────────────────────────────────────────────────
    try:
        ms_token = OAuthToken.objects.get(user=request.user, provider=OAuthToken.PROVIDER_MICROSOFT)
        ms_access_token = _refresh_microsoft_token_if_needed(ms_token)
        
        now = timezone.now()
        # Use ISO format for MS Graph (Z is required)
        start_date_time = (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_date_time = (now + timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%SZ')

        resp = requests.get(
            f"{MS_GRAPH_URL}/me/calendarView?startDateTime={start_date_time}&endDateTime={end_date_time}&$select=id,subject,start,end,onlineMeeting,webLink",
            headers={"Authorization": f"Bearer {ms_access_token}"},
        )
        
        if resp.ok:
            items = resp.json().get("value", [])
            for item in items:
                events.append({
                    "id": f"microsoft_{item.get('id')}",
                    "title": item.get("subject", "No Title"),
                    "start": item.get("start", {}).get("dateTime"),
                    "end": item.get("end", {}).get("dateTime"),
                    "meeting_url": item.get("onlineMeeting", {}).get("joinUrl") if item.get("onlineMeeting") else None,
                    "html_link": item.get("webLink"),
                    "provider": "microsoft",
                })
        else:
            logger.error(f"Microsoft Calendar fetch failed: {resp.text}")
    except OAuthToken.DoesNotExist:
        pass

    return Response({"events": events})
