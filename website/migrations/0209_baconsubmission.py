# Generated by Django 5.1.5 on 2025-02-26 19:47

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0208_alter_points_created"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BaconSubmission",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("github_url", models.URLField()),
                (
                    "contribution_type",
                    models.CharField(
                        choices=[("security", "Security Related"), ("non-security", "Non-Security Related")],
                        max_length=20,
                    ),
                ),
                ("description", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("in_review", "In Review"), ("accepted", "Accepted"), ("declined", "Declined")],
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "transaction_status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("completed", "Completed")], default="pending", max_length=20
                    ),
                ),
                ("transaction_id", models.CharField(blank=True, max_length=255, null=True)),
                ("bacon_amount", models.IntegerField(default=0)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
