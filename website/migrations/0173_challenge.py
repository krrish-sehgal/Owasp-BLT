# Generated by Django 5.1.3 on 2024-12-18 18:54

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0172_merge_20241218_0505"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Challenge",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField()),
                (
                    "challenge_type",
                    models.CharField(
                        choices=[("single", "Single User"), ("team", "Team")],
                        default="single",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("points", models.IntegerField(default=0)),
                ("progress", models.IntegerField(default=0)),
                ("completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "participants",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_challenges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team_participants",
                    models.ManyToManyField(
                        blank=True, related_name="team_challenges", to="website.organization"
                    ),
                ),
            ],
        ),
    ]
