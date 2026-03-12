from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='OAuthToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('google', 'Google'), ('microsoft', 'Microsoft')], max_length=20)),
                ('access_token', models.TextField()),
                ('refresh_token', models.TextField(blank=True)),
                ('token_expiry', models.DateTimeField(blank=True, null=True)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='oauth_tokens', to='authentication.user')),
            ],
            options={
                'db_table': 'oauth_tokens',
                'unique_together': {('user', 'provider')},
            },
        ),
    ]
