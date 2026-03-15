from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('standup', '0001_initial'),
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('commits', models.JSONField(default=list)),
                ('pull_requests', models.JSONField(default=list)),
                ('tasks_completed', models.JSONField(default=list)),
                ('tasks_in_progress', models.JSONField(default=list)),
                ('meetings', models.JSONField(default=list)),
                ('notes_count', models.PositiveIntegerField(default=0)),
                ('timeline', models.JSONField(default=list)),
                ('ai_summary', models.TextField(blank=True)),
                ('total_commits', models.PositiveIntegerField(default=0)),
                ('total_prs', models.PositiveIntegerField(default=0)),
                ('total_tasks_done', models.PositiveIntegerField(default=0)),
                ('total_meetings', models.PositiveIntegerField(default=0)),
                ('total_meeting_minutes', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_reports', to='authentication.user')),
            ],
            options={
                'db_table': 'daily_reports',
                'ordering': ['-date'],
                'unique_together': {('user', 'date')},
            },
        ),
    ]
