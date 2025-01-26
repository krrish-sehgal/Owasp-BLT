# Generated by Django 5.1.3 on 2024-12-18 13:12

from django.db import migrations


def add_team_challenges(apps, schema_editor):
    Challenge = apps.get_model("website", "Challenge")

    # Define the team challenges
    team_challenges = [
        {
            "title": "Report 10 IPs",
            "description": "Report 10 different suspicious IPs as a team to complete this challenge.",
            "challenge_type": "team",
            "points": 1,
        },
        {
            "title": "Report 10 Issues",
            "description": "Report 10 unique issues as a team to complete this challenge.",
            "challenge_type": "team",
            "points": 1,
        },
        {
            "title": "All Members Sign in for 5 Days",
            "description": "Ensure all team members sign in for 5 consecutive days to complete this challenge.",
            "challenge_type": "team",
            "points": 1,
        },
    ]

    # Insert challenges into the Challenge model
    for challenge in team_challenges:
        Challenge.objects.create(
            title=challenge["title"],
            description=challenge["description"],
            challenge_type=challenge["challenge_type"],
            points=challenge["points"],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0174_add_single_user_challenges"),
    ]

    operations = [
        migrations.RunPython(add_team_challenges),
    ]
