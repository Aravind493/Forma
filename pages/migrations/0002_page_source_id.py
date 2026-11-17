from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[("pages","0001_initial")]
    operations=[migrations.AddField(model_name="page",name="source_id",field=models.CharField(blank=True,db_index=True,default="",max_length=64))]
