import requests
import json
from datetime import date, datetime, timedelta

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Standup, DailyReport
from .serializers import StandupSerializer, DailyReportSerializer


# ── GitHub helpers ────────────────────────────────────────────────────────────

def fetch_github_activity(user, days=1):
    """
    Fetch recent commits AND pull requests from GitHub.
    Returns { commits: [...], pull_requests: [...] }
    Each commit: { time, repo, message }
    Each PR:     { time, repo, title, action, url }
    """
    token = user.github_access_token
    username = user.github_username
    if not token:
        return {"commits": [], "pull_requests": []}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    commits = []
    pull_requests = []
    since_dt = datetime.utcnow() - timedelta(days=days)
    since_str = since_dt.isoformat() + "Z"

    try:
        # ── Events API: PRs ──────────────────────────────────────
        events_resp = requests.get(
            "https://api.github.com/user/events?per_page=100",
            headers=headers,
            timeout=15,
        )
        if events_resp.status_code == 200:
            for event in events_resp.json():
                event_time_str = event.get("created_at", "")
                try:
                    event_time = datetime.strptime(event_time_str, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    continue
                if event_time < since_dt:
                    continue

                repo = event.get("repo", {}).get("name", "unknown")
                payload = event.get("payload", {})

                if event["type"] == "PullRequestEvent":
                    pr = payload.get("pull_request", {})
                    action = payload.get("action", "")
                    if action in ("opened", "closed", "reopened", "merged"):
                        pull_requests.append({
                            "time": event_time_str,
                            "repo": repo,
                            "title": pr.get("title", ""),
                            "action": action,
                            "url": pr.get("html_url", ""),
                            "number": pr.get("number"),
                        })

        # ── Commits API: per repo ────────────────────────────────
        repos_resp = requests.get(
            "https://api.github.com/user/repos?per_page=50&sort=pushed",
            headers=headers,
            timeout=15,
        )
        if repos_resp.status_code == 200:
            repos = repos_resp.json()
            for repo in repos[:15]:  # limit to 15 most recently pushed repos
                owner = repo["owner"]["login"]
                repo_name = repo["name"]
                commits_resp = requests.get(
                    f"https://api.github.com/repos/{owner}/{repo_name}/commits",
                    headers=headers,
                    params={"since": since_str, "author": username, "per_page": 30},
                    timeout=10,
                )
                if commits_resp.status_code != 200:
                    continue
                for c in commits_resp.json():
                    commit_data = c.get("commit", {})
                    author = commit_data.get("author", {})
                    commit_time = author.get("date", "")
                    message = commit_data.get("message", "").split("\n")[0]
                    commits.append({
                        "time": commit_time,
                        "repo": repo_name,
                        "message": message,
                        "sha": c.get("sha", "")[:7],
                        "url": c.get("html_url", ""),
                    })

        commits = commits[:30]

    except Exception:
        pass

    return {"commits": commits, "pull_requests": pull_requests}


def fetch_github_commits(user, days=1):
    """Legacy helper used by standup generator — returns flat list of strings."""
    activity = fetch_github_activity(user, days=days)
    result = []
    for c in activity["commits"]:
        result.append(f"[{c['repo']}] {c['message']}")
    for pr in activity["pull_requests"]:
        result.append(f"[{pr['repo']}] PR {pr['action']}: {pr['title']}")
    return result[:20]


# ── Daily Report ──────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_daily_report(request):
    """
    Generate a full Daily Dev Activity Report.
    POST body: { "date": "YYYY-MM-DD" (optional, defaults to today) }
    """
    user = request.user
    report_date_str = request.data.get("date", str(date.today()))
    try:
        report_date = date.fromisoformat(report_date_str)
    except ValueError:
        report_date = date.today()

    days_ago = (date.today() - report_date).days + 1

    # 1. GitHub activity
    github_activity = fetch_github_activity(user, days=days_ago)
    commits = github_activity["commits"]
    pull_requests = github_activity["pull_requests"]

    # 2. Tasks
    from apps.tasks.models import Task
    all_tasks = Task.objects.filter(user=user).order_by("-updated_at")[:50]
    tasks_done = [
        {"title": t.title, "time": t.updated_at.isoformat(), "status": "done"}
        for t in all_tasks if t.status == "done"
    ]
    tasks_wip = [
        {"title": t.title, "time": t.updated_at.isoformat(), "status": "in_progress"}
        for t in all_tasks if t.status == "in_progress"
    ]

    # 3. Meetings
    from apps.meetings.models import Meeting
    recent_meetings = Meeting.objects.filter(
        user=user, status="done"
    ).order_by("-created_at")[:10]
    meetings_data = [
        {
            "title": m.title,
            "time": m.created_at.isoformat(),
            "duration_seconds": m.duration_seconds or 0,
            "duration_display": m.duration_display or "—",
            "task_count": m.tasks.count() if hasattr(m, "tasks") else 0,
        }
        for m in recent_meetings
    ]
    total_meeting_minutes = sum(
        m["duration_seconds"] // 60 for m in meetings_data
    )

    # 4. Build timeline (sorted by time)
    timeline_events = []

    for c in commits:
        if c.get("time"):
            timeline_events.append({
                "time": c["time"],
                "type": "commit",
                "icon": "⌥",
                "title": f"[{c['repo']}] {c['message']}",
                "meta": c.get("sha", ""),
            })

    for pr in pull_requests:
        if pr.get("time"):
            action_icons = {"opened": "🔀", "merged": "✅", "closed": "❌", "reopened": "🔄"}
            timeline_events.append({
                "time": pr["time"],
                "type": "pr",
                "icon": action_icons.get(pr["action"], "🔀"),
                "title": f"PR {pr['action']}: {pr['title']}",
                "meta": pr["repo"],
            })

    for t in tasks_done[:5]:
        timeline_events.append({
            "time": t["time"],
            "type": "task",
            "icon": "✓",
            "title": t["title"],
            "meta": "completed",
        })

    for m in meetings_data[:5]:
        timeline_events.append({
            "time": m["time"],
            "type": "meeting",
            "icon": "◈",
            "title": m["title"],
            "meta": m["duration_display"],
        })

    # Sort timeline by time descending (most recent first)
    def parse_time(t):
        ts = t.get("time", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    timeline_events.sort(key=parse_time, reverse=True)

    # 5. AI summary
    ai_summary = ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        commits_text = "\n".join(
            f"- [{c['repo']}] {c['message']}" for c in commits[:10]
        ) or "No commits."
        prs_text = "\n".join(
            f"- PR {pr['action']}: {pr['title']} ({pr['repo']})" for pr in pull_requests[:5]
        ) or "No PRs."
        tasks_text = "\n".join(
            f"- {t['title']}" for t in tasks_done[:5]
        ) or "No completed tasks."
        meetings_text = "\n".join(
            f"- {m['title']} ({m['duration_display']})" for m in meetings_data[:3]
        ) or "No meetings."

        prompt = f"""You are a developer productivity assistant. Write a concise, friendly Daily Activity Summary for a developer based on their activity today.

Structure:
1. One paragraph overview (2-3 sentences) of what they worked on
2. Key highlights (3-5 bullet points max)
3. One sentence about tomorrow's focus based on in-progress work

Keep it under 120 words total. Be specific, mention repo names and PR titles. Friendly tone.

Activity for {report_date_str}:

Commits:
{commits_text}

Pull Requests:
{prs_text}

Tasks Completed:
{tasks_text}

Meetings:
{meetings_text}

Write the summary now:"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=250,
        )
        ai_summary = resp.choices[0].message.content.strip()
    except Exception:
        # Plain fallback
        ai_summary = (
            f"On {report_date_str}: made {len(commits)} commit(s), "
            f"{len(pull_requests)} PR action(s), "
            f"completed {len(tasks_done)} task(s), "
            f"attended {len(meetings_data)} meeting(s)."
        )

    # 6. Save/update report
    report, _ = DailyReport.objects.update_or_create(
        user=user,
        date=report_date,
        defaults={
            "commits": commits,
            "pull_requests": pull_requests,
            "tasks_completed": tasks_done,
            "tasks_in_progress": tasks_wip,
            "meetings": meetings_data,
            "notes_count": 0,  # notes are in localStorage; client can pass this
            "timeline": timeline_events,
            "ai_summary": ai_summary,
            "total_commits": len(commits),
            "total_prs": len(pull_requests),
            "total_tasks_done": len(tasks_done),
            "total_meetings": len(meetings_data),
            "total_meeting_minutes": total_meeting_minutes,
        },
    )

    return Response(DailyReportSerializer(report).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daily_report_list(request):
    reports = DailyReport.objects.filter(user=request.user)
    return Response({"results": DailyReportSerializer(reports, many=True).data})


@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def daily_report_detail(request, pk):
    try:
        report = DailyReport.objects.get(pk=pk, user=request.user)
    except DailyReport.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(DailyReportSerializer(report).data)
    report.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Standup views ─────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_standup(request):
    user = request.user
    standup_date = request.data.get("date", str(date.today()))

    commits_list = fetch_github_commits(user, days=1)

    from apps.tasks.models import Task
    recent_tasks = Task.objects.filter(
        user=user, status__in=["done", "in_progress"]
    ).order_by("-updated_at")[:10]
    task_lines = [f"- {t.title} [{t.status}]" for t in recent_tasks]

    from apps.meetings.models import Meeting
    recent_meetings = Meeting.objects.filter(
        user=user, status="done"
    ).order_by("-created_at")[:5]
    meeting_lines = [f"- {m.title}" for m in recent_meetings]

    commits_text = "\n".join(commits_list) if commits_list else "No commits found."
    tasks_text = "\n".join(task_lines) if task_lines else "No tasks found."
    meetings_text = "\n".join(meeting_lines) if meeting_lines else "No meetings found."

    prompt = f"""Generate a concise developer standup update based on the following activity.
Write it in first person, professional tone. Use 3 sections: Yesterday, Today, Blockers.
Keep it under 150 words total.

Git Commits / PRs:
{commits_text}

Tasks (completed / in progress):
{tasks_text}

Recent Meetings:
{meetings_text}

Return only the standup text, no headings like "Standup:" or markdown formatting."""

    standup_content = ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=300,
        )
        standup_content = response.choices[0].message.content.strip()
    except Exception:
        standup_content = (
            f"Yesterday:\n{commits_text}\n\nToday:\n{tasks_text}\n\nBlockers:\nNone."
        )

    standup, _ = Standup.objects.update_or_create(
        user=user,
        date=standup_date,
        defaults={
            "content": standup_content,
            "commits_summary": commits_text,
            "tasks_summary": tasks_text,
            "meetings_summary": meetings_text,
        },
    )

    return Response(StandupSerializer(standup).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def standup_list(request):
    standups = Standup.objects.filter(user=request.user)
    return Response({"results": StandupSerializer(standups, many=True).data})


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def standup_detail(request, pk):
    try:
        standup = Standup.objects.get(pk=pk, user=request.user)
    except Standup.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(StandupSerializer(standup).data)
    if request.method == "PATCH":
        serializer = StandupSerializer(standup, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    standup.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_commits(request):
    days = int(request.query_params.get("days", 1))
    activity = fetch_github_activity(request.user, days=days)
    flat = fetch_github_commits(request.user, days=days)
    return Response({
        "commits": flat,
        "commits_detail": activity["commits"],
        "pull_requests": activity["pull_requests"],
        "connected": bool(request.user.github_access_token),
    })
