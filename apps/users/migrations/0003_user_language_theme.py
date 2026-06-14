from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_userdepartment_multi_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="language",
            field=models.CharField(
                choices=[("en", "English"), ("sw", "Swahili")],
                default="en",
                max_length=5,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="theme",
            field=models.CharField(
                choices=[("dark", "Dark"), ("light", "Light")],
                default="dark",
                max_length=5,
            ),
        ),
    ]
