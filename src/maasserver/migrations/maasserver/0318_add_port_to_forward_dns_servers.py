# Generated by Django 3.2.12 on 2024-03-07 17:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maasserver", "0317_migrate_defaultresource_zone"),
    ]

    operations = [
        migrations.AddField(
            model_name="forwarddnsserver",
            name="port",
            field=models.IntegerField(default=53),
        ),
    ]