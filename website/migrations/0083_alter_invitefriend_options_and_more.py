# Generated by Django 5.0.2 on 2024-02-25 15:28

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0082_issue_reporter_ip_address"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="invitefriend",
            options={},
        ),
        migrations.RemoveField(
            model_name="invitefriend",
            name="recipient",
        ),
        migrations.RemoveField(
            model_name="invitefriend",
            name="sent",
        ),
        migrations.AddField(
            model_name="invitefriend",
            name="point_by_referral",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="invitefriend",
            name="recipients",
            field=models.ManyToManyField(blank=True, related_name="received_invites", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="invitefriend",
            name="referral_code",
            field=models.CharField(default=uuid.uuid4, editable=False, max_length=100),
        ),
        migrations.AlterField(
            model_name="invitefriend",
            name="sender",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sent_invites",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
