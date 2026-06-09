from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inspection", "0012_employee"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="user_type",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "SuperAdmin"),
                    (2, "Admin"),
                    (3, "User"),
                    (4, "Viewer"),
                ]
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="parentProject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subProjects",
                to="inspection.project",
            ),
        ),
    ]
