# Generated by Django 5.1.3 on 2024-11-28 19:23

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0159_merge_20241128_0439"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="dislike_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activity",
            name="dislikes",
            field=models.ManyToManyField(
                blank=True,
                related_name="disliked_activities",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="activity",
            name="is_approved",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="is_posted_to_bluesky",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="like_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="activity",
            name="likes",
            field=models.ManyToManyField(
                blank=True, related_name="liked_activities", to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AlterField(
            model_name="badge",
            name="icon",
            field=models.ImageField(blank=True, null=True, upload_to="badges/"),
        ),
    ]