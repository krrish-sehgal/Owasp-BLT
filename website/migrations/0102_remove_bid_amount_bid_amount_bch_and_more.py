# Generated by Django 5.0.6 on 2024-08-02 18:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0101_alter_bid_user"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="bid",
            name="amount",
        ),
        migrations.AddField(
            model_name="bid",
            name="amount_bch",
            field=models.DecimalField(decimal_places=8, default=0, max_digits=16),
        ),
        migrations.AlterField(
            model_name="project",
            name="contributors",
            field=models.ManyToManyField(blank=True, related_name="projects", to="website.contributor"),
        ),
    ]
