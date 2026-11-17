from django.db import migrations

class Migration(migrations.Migration):
    dependencies=[("pages","0002_page_source_id")]
    operations=[migrations.AlterModelOptions(name="page",options={"ordering":["-updated_at"]})]
