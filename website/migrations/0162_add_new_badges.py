# Generated by Django 5.1.3 on 2024-11-30 14:15

from django.db import migrations


def add_new_badges(apps, schema_editor):
    # Get the Badge model
    Badge = apps.get_model("website", "Badge")
    
    # Define the new badges to add
    new_badges = [
        {"title": "First IP Reported", "description": "Awarded for reporting the first intellectual property.", "type": "automatic"},
        {"title": "First Bid Placed", "description": "Awarded for placing the first bid.", "type": "manual"},
        {"title": "First Bug Bounty", "description": "Awarded for earning the first bug bounty.", "type": "manual"},
        {"title": "First Suggestion", "description": "Awarded for making the first suggestion.", "type": "manual"},
    ]
    
    # Loop through the new badges and create them if they don't already exist
    for badge in new_badges:
        Badge.objects.get_or_create(
            title=badge["title"],
            defaults={
                "description": badge["description"],
                "type": badge["type"],
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0161_alter_badge_icon"),  # Adjust based on your actual previous migration
    ]

    operations = [
        migrations.RunPython(add_new_badges),
    ]
