from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_user_language_theme"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="theme",
            field=models.CharField(
                choices=[("dark", "Dark"), ("light", "Light")],
                default="light",
                max_length=5,
            ),
        ),
    ]
