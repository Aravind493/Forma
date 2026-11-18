import uuid
from django.conf import settings
from django.db import models
class Workspace(models.Model):
    name=models.CharField(max_length=120); slug=models.SlugField(max_length=140,unique=True)
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="owned_workspaces")
    members=models.ManyToManyField(settings.AUTH_USER_MODEL,through="Membership",related_name="workspaces")
    created_at=models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name
class Membership(models.Model):
    ROLE_CHOICES=[("owner","Owner"),("editor","Editor"),("viewer","Viewer")]
    workspace=models.ForeignKey(Workspace,on_delete=models.CASCADE); user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    role=models.CharField(max_length=12,choices=ROLE_CHOICES,default="editor"); joined_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["workspace","user"],name="unique_workspace_member")]

class Profile(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="profile")
    bio=models.CharField(max_length=500,blank=True)
    job_title=models.CharField(max_length=120,blank=True)
    location=models.CharField(max_length=120,blank=True)
    website=models.URLField(max_length=300,blank=True)
    updated_at=models.DateTimeField(auto_now=True)
    def __str__(self): return f"{self.user.username}'s profile"

class Page(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    workspace=models.ForeignKey(Workspace,on_delete=models.CASCADE,related_name="pages")
    parent=models.ForeignKey("self",on_delete=models.CASCADE,null=True,blank=True,related_name="children")
    title=models.CharField(max_length=300,default="Untitled"); icon=models.CharField(max_length=16,default="📄")
    content=models.JSONField(default=list,blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,related_name="created_pages")
    updated_at=models.DateTimeField(auto_now=True); created_at=models.DateTimeField(auto_now_add=True)
    is_favorite=models.BooleanField(default=False); is_archived=models.BooleanField(default=False)
    share_token=models.UUIDField(null=True,blank=True,unique=True)
    source_id=models.CharField(max_length=64,blank=True,default="",db_index=True)
    class Meta: ordering=["-updated_at"]
    def __str__(self): return self.title
