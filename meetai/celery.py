import os
from celery import Celery
from dotenv import load_dotenv

# Load .env BEFORE Django settings are read — critical for local dev
load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "meetai.settings")

app = Celery("meetai")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
