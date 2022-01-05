# Generated by Django 2.2.12 on 2022-01-04 13:48

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone

import maasserver.models.cleansave


def create_default_nodeconfigs(apps, schema_editor):
    Node = apps.get_model("maasserver", "Node")
    NodeConfig = apps.get_model("maasserver", "NodeConfig")
    now = timezone.now()
    NodeConfig.objects.bulk_create(
        [
            NodeConfig(node_id=node_id, created=now, updated=now)
            for node_id in Node.objects.all().values_list("id", flat=True)
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("maasserver", "0252_drop_fannetwork"),
    ]

    operations = [
        migrations.CreateModel(
            name="NodeConfig",
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
                ("created", models.DateTimeField(editable=False)),
                ("updated", models.DateTimeField(editable=False)),
                (
                    "name",
                    models.TextField(
                        choices=[
                            ("discovered", "discovered"),
                            ("deployment", "deployment"),
                        ],
                        default="discovered",
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="maasserver.Node",
                    ),
                ),
            ],
            options={
                "unique_together": {("node", "name")},
            },
            bases=(maasserver.models.cleansave.CleanSave, models.Model),
        ),
        migrations.AddField(
            model_name="blockdevice",
            name="node_config",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="maasserver.NodeConfig",
            ),
        ),
        migrations.AddField(
            model_name="filesystem",
            name="node_config",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="maasserver.NodeConfig",
            ),
        ),
        migrations.AddField(
            model_name="interface",
            name="node_config",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="maasserver.NodeConfig",
            ),
        ),
        migrations.RunPython(create_default_nodeconfigs),
    ]
