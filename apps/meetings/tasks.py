import json
import logging
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    time_limit=600,
    soft_time_limit=540,
)
def process_meeting(self, meeting_id):
    """
    Main pipeline: transcribe audio → AI analysis → extract tasks.
    """
    from .models import Meeting, Transcript, MeetingSummary, MeetingDecision
    from apps.tasks.models import Task

    try:
        meeting = Meeting.objects.get(id=meeting_id)
    except Meeting.DoesNotExist:
        print("ELSEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE")
        logger.error(f"Meeting {meeting_id} not found")
        return

    try:
        # Step 1: Transcribe
        print("TRYRRRRRRRRRRRRRRRRRRRRRRRRRRRRR")
        meeting.status = Meeting.STATUS_TRANSCRIBING
        meeting.save(update_fields=["status"])
        print("ENTERRRRRRRRRRRRRRRRRRRRRR")
        transcript_text = transcribe_audio(meeting)
        print("AFTER TRANSCRIBEEEEEEEEEEEEEEEEEEEEE", transcript_text)
        transcript, _ = Transcript.objects.update_or_create(
            meeting=meeting,
            defaults={"text": transcript_text},
        )

        # Step 2: AI Analysis
        meeting.status = Meeting.STATUS_ANALYZING
        meeting.save(update_fields=["status"])

        analysis = analyze_transcript(transcript_text, meeting.title)

        # Save summary
        MeetingSummary.objects.update_or_create(
            meeting=meeting,
            defaults={
                "summary_text": analysis.get("summary", ""),
                "next_steps": analysis.get("next_steps", ""),
            },
        )

        # Save decisions
        MeetingDecision.objects.filter(meeting=meeting).delete()
        for i, d in enumerate(analysis.get("decisions", [])):
            MeetingDecision.objects.create(
                meeting=meeting, decision_text=d, order=i
            )

        # Save tasks
        Task.objects.filter(meeting=meeting).delete()
        for t in analysis.get("tasks", []):
            Task.objects.create(
                meeting=meeting,
                user=meeting.user,
                title=t.get("title", ""),
                description=t.get("description", ""),
                assigned_to=t.get("assigned_to", ""),
                due_date=t.get("due_date") or None,
                status=Task.STATUS_TODO,
            )

        meeting.status = Meeting.STATUS_DONE
        meeting.save(update_fields=["status", "updated_at"])

        # Increment user's meeting count
        meeting.user.meetings_this_month += 1
        meeting.user.save(update_fields=["meetings_this_month"])

        logger.info(f"Meeting {meeting_id} processed successfully.")

    except Exception as exc:
        logger.exception(f"Error processing meeting {meeting_id}: {exc}")
        meeting.status = Meeting.STATUS_FAILED
        meeting.error_message = str(exc)
        meeting.save(update_fields=["status", "error_message"])


def transcribe_audio(meeting):
    print("INSIDE TRANSCRIBE AUDIO", meeting.recording_file)
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        logger.info("No API key found")
        print("NO API KEY FOUND")
        return _mock_transcript(meeting.title)

    if not meeting.recording_file:
        logger.warning("No recording file attached.")
        print("NO RECORDING FILE ATTACHED")
        return _mock_transcript(meeting.title)

    try:
        print("TRYING TO TRANSCRIBE AUDIO WITH OPENAI")
        import httpx
        from openai import OpenAI

        # Create client without proxies — compatible with openai v1.55+ and v2
        http_client = httpx.Client()
        client = OpenAI(api_key=api_key, http_client=http_client)

        file_name = meeting.recording_file.name.split("/")[-1]
        with meeting.recording_file.open("rb") as audio_file:
            audio_bytes = audio_file.read()
        print("GOT AUDIO BYTES, SENDING TO OPENAI", len(audio_bytes))
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file_name, audio_bytes),
        )

        print("RECEIVED RESPONSE", response.text)

        # Always return a plain string
        return response.text if hasattr(response, "text") else str(response)

    except Exception as e:
        logger.warning(f"Whisper transcription failed: {e}. Using mock.")
        return _mock_transcript(meeting.title)


def analyze_transcript(transcript_text, meeting_title):
    """
    Analyze transcript using GPT-4 to extract structured data.
    Falls back to mock analysis if no API key configured.
    """
    api_key = settings.OPENAI_API_KEY
    if not api_key or api_key.startswith("sk-your"):
        return _mock_analysis(meeting_title)

    try:
        import httpx
        from openai import OpenAI

        http_client = httpx.Client()
        client = OpenAI(api_key=api_key, http_client=http_client)

        prompt = f"""Analyze the following meeting transcript and return a JSON object with:
- "summary": A concise 2-3 sentence summary of the meeting
- "decisions": An array of key decisions made (strings)
- "tasks": An array of action items, each with:
  - "title": task title
  - "description": brief description
  - "assigned_to": person responsible (or "" if not mentioned)
  - "due_date": ISO date string or null
- "next_steps": A brief paragraph on recommended next steps

Return ONLY valid JSON, no markdown, no preamble.

Transcript:
{transcript_text[:8000]}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from GPT. Falling back to mock.")
            return _mock_analysis(meeting_title)
    except Exception as e:
        logger.warning(f"GPT analysis failed: {e}. Using mock.")
        return _mock_analysis(meeting_title)


def _mock_transcript(title):
    return (
        f"This is an auto-generated transcript for '{title}'. "
        "The team discussed project milestones and assigned responsibilities. "
        "John will handle the backend setup. Sarah will prepare UI mockups. "
        "Alex will define the API endpoints by end of week. "
        "The team agreed to use PostgreSQL and decided to delay launch by two weeks. "
        "Next sync is scheduled for Friday at 10am."
    )


def _mock_analysis(title):
    return {
        "summary": f"Team meeting discussing '{title}'. Responsibilities assigned and technical decisions made.",
        "decisions": [
            "Use PostgreSQL as the primary database",
            "Delay product launch by 2 weeks for quality assurance",
            "Hold weekly syncs every Friday at 10am",
        ],
        "tasks": [
            {"title": "Setup backend repository", "description": "Initialize and configure the backend repo.", "assigned_to": "John", "due_date": None},
            {"title": "Prepare UI mockups", "description": "Design mockups for all main screens.", "assigned_to": "Sarah", "due_date": None},
            {"title": "Define API endpoints", "description": "Document all REST API endpoints.", "assigned_to": "Alex", "due_date": None},
        ],
        "next_steps": "Review all assigned tasks in the next Friday sync. Ensure all deliverables are on track.",
    }
