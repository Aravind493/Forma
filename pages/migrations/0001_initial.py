import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial=True
    dependencies=[migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name="Workspace",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("name",models.CharField(max_length=120)),("slug",models.SlugField(max_length=140,unique=True)),("created_at",models.DateTimeField(auto_now_add=True)),("owner",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="owned_workspaces",to=settings.AUTH_USER_MODEL))]),
        migrations.CreateModel(name="Membership",fields=[("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),("role",models.CharField(choices=[("owner","Owner"),("editor","Editor"),("viewer","Viewer")],default="editor",max_length=12)),("joined_at",models.DateTimeField(auto_now_add=True)),("user",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to=settings.AUTH_USER_MODEL)),("workspace",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to="pages.workspace"))]),
        migrations.CreateModel(name="Page",fields=[("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),("title",models.CharField(default="Untitled",max_length=300)),("icon",models.CharField(default="📄",max_length=16)),("content",models.JSONField(blank=True,default=list)),("updated_at",models.DateTimeField(auto_now=True)),("created_at",models.DateTimeField(auto_now_add=True)),("is_favorite",models.BooleanField(default=False)),("is_archived",models.BooleanField(default=False)),("share_token",models.UUIDField(blank=True,null=True,unique=True)),("created_by",models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,related_name="created_pages",to=settings.AUTH_USER_MODEL)),("parent",models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.CASCADE,related_name="children",to="pages.page")),("workspace",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="pages",to="pages.workspace"))]),
        migrations.AddField(model_name="workspace",name="members",field=models.ManyToManyField(related_name="workspaces",through="pages.Membership",to=settings.AUTH_USER_MODEL)),
        migrations.AddConstraint(model_name="membership",constraint=models.UniqueConstraint(fields=("workspace","user"),name="unique_workspace_member")),
    ]
