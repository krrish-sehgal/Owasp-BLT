# Generated by Django 5.1.3 on 2024-12-16 12:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fresh", "0008_add_challenges"),
    ]

    operations = [
        migrations.AddField(
            model_name="challenge",
            name="progress",
            field=models.IntegerField(default=0),
        ),
    ]