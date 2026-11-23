from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0005_inline_child_page_references"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="avatar",
            field=models.ImageField(blank=True, upload_to="profile_avatars/"),
        ),
    ]
