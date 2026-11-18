import json
from collections import defaultdict
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST
from .models import Workspace, Membership, Page, Profile
from .forms import AccountDetailsForm, ProfileDetailsForm
from .notion_import import import_notion_export, MAX_BYTES

def _workspace(user):
    member=Membership.objects.filter(user=user).select_related("workspace").first()
    return member.workspace if member else None

def _page_navigation(workspace):
    pages=list(workspace.pages.filter(is_archived=False).order_by("created_at","title"))
    ids={page.id for page in pages}; children=defaultdict(list); roots=[]
    for page in pages:
        if page.parent_id in ids: children[page.parent_id].append(page)
        else: roots.append(page)
    parent_ids={page.parent_id for page in pages if page.parent_id in ids}
    result=[]; visited=set()
    def add(page,depth):
        if page.id in visited: return
        visited.add(page.id); result.append({"page":page,"level":depth,"indent":depth*14,"has_children":page.id in parent_ids})
        for child in children[page.id]: add(child,depth+1)
    for root in roots: add(root,0)
    for page in pages: add(page,0)
    return result

def _new_workspace(user):
    base=slugify(user.username) or "workspace"; slug=base; i=2
    while Workspace.objects.filter(slug=slug).exists(): slug=f"{base}-{i}"; i+=1
    workspace=Workspace.objects.create(name=f"{user.username}'s workspace",slug=slug,owner=user)
    Membership.objects.create(workspace=workspace,user=user,role="owner")
    return workspace

def _starter(workspace,user):
    if workspace.pages.exists(): return
    Page.objects.create(workspace=workspace,created_by=user,title="Welcome to your workspace",icon="👋",content=[{"type":"heading_1","text":"A calmer place to think"},{"type":"paragraph","text":"Your pages, notes, and plans live here. Start writing, or import your Notion export from the sidebar."},{"type":"heading_2","text":"A few things to try"},{"type":"to_do","text":"Create a page for a project","checked":False},{"type":"to_do","text":"Save an idea before it gets away","checked":False},{"type":"callout","text":"Tip: type / in the editor to add a block."}])

def signup(request):
    if request.method=="POST":
        form=UserCreationForm(request.POST)
        if form.is_valid():
            user=form.save(); login(request,user); ws=_new_workspace(user); _starter(ws,user); return redirect("home")
    else: form=UserCreationForm()
    return render(request,"registration/signup.html",{"form":form})

@login_required
def home(request):
    workspace=_workspace(request.user) or _new_workspace(request.user); _starter(workspace,request.user)
    page=workspace.pages.filter(is_archived=False).first()
    return redirect("page",page_id=page.id) if page else redirect("import_notion")

@login_required
def page_view(request,page_id):
    workspace=_workspace(request.user)
    page=get_object_or_404(Page.objects.select_related("workspace"),id=page_id,workspace=workspace,is_archived=False)
    return render(request,"pages/editor.html",{"workspace":workspace,"page_tree":_page_navigation(workspace),"page":page})

@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    workspace = _workspace(request.user)
    if request.method == "POST":
        account_form = AccountDetailsForm(request.POST, instance=request.user)
        profile_form = ProfileDetailsForm(request.POST, instance=profile)
        if account_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                account_form.save()
                profile_form.save()
            messages.success(request, "Your profile has been saved.")
            return redirect("profile")
    else:
        account_form = AccountDetailsForm(instance=request.user)
        profile_form = ProfileDetailsForm(instance=profile)
    return render(request, "pages/profile.html", {
        "workspace": workspace,
        "account_form": account_form,
        "profile_form": profile_form,
        "page_count": workspace.pages.count() if workspace else 0,
    })

def shared_page(request,share_token):
    page=get_object_or_404(Page.objects.select_related("workspace"),share_token=share_token,is_archived=False)
    return render(request,"pages/shared.html",{"page":page})

@login_required
@require_http_methods(["POST","DELETE"])
def share_page(request,page_id):
    workspace=_workspace(request.user); page=get_object_or_404(Page,id=page_id,workspace=workspace)
    if Membership.objects.get(workspace=workspace,user=request.user).role=="viewer": return JsonResponse({"error":"Only editors can share this page"},status=403)
    if request.method=="DELETE":
        page.share_token=None; page.save(update_fields=["share_token"]); return JsonResponse({"shared":False})
    if not page.share_token:
        page.share_token=uuid.uuid4(); page.save(update_fields=["share_token"])
    return JsonResponse({"shared":True,"url":request.build_absolute_uri(f"/share/{page.share_token}/")})

@login_required
@require_POST
def create_page(request):
    workspace=_workspace(request.user)
    if not workspace: return JsonResponse({"error":"Workspace not found"},status=404)
    try: data=json.loads(request.body or "{}")
    except ValueError: return HttpResponseBadRequest("Invalid JSON")
    parent=None
    if data.get("parent"): parent=get_object_or_404(Page,id=data["parent"],workspace=workspace)
    page=Page.objects.create(workspace=workspace,created_by=request.user,parent=parent,title="Untitled",icon="📄")
    return JsonResponse({"id":str(page.id),"url":f"/page/{page.id}/"},status=201)

@login_required
@require_http_methods(["PATCH"])
def update_page(request,page_id):
    workspace=_workspace(request.user); page=get_object_or_404(Page,id=page_id,workspace=workspace)
    member=Membership.objects.get(workspace=workspace,user=request.user)
    if member.role=="viewer": return JsonResponse({"error":"Read only"},status=403)
    try: data=json.loads(request.body)
    except (ValueError,TypeError): return HttpResponseBadRequest("Invalid JSON")
    if "title" in data: page.title=str(data["title"])[:300]
    if "icon" in data: page.icon=str(data["icon"])[:16]
    if "content" in data:
        if not isinstance(data["content"],list) or len(data["content"])>5000: return HttpResponseBadRequest("Invalid content")
        allowed={"paragraph","heading_1","heading_2","heading_3","bulleted_list","numbered_list","quote","callout","code","to_do","toggle","image","file","page_link","link","table","divider"}
        for block in data["content"]:
            if not isinstance(block,dict) or block.get("type") not in allowed or not isinstance(block.get("text",""),str) or len(block.get("text",""))>20000: return HttpResponseBadRequest("Invalid block content")
            kind=block["type"]; url=block.get("url","")
            if kind in {"image","file","page_link","link"} and not isinstance(url,str): return HttpResponseBadRequest("Invalid block URL")
            if kind=="file" and not url.startswith("/media/"): return HttpResponseBadRequest("Invalid file URL")
            if kind=="page_link" and not url.startswith("/page/"): return HttpResponseBadRequest("Invalid page link")
            if kind=="link" and not (url.startswith(("https://","http://","mailto:","/page/","/media/"))): return HttpResponseBadRequest("Invalid link URL")
            if kind=="image" and url and not url.startswith(("https://","http://","/media/")): return HttpResponseBadRequest("Invalid image URL")
            if kind=="table":
                rows=block.get("rows",[])
                if not isinstance(rows,list) or len(rows)>2000 or any(not isinstance(row,list) or len(row)>100 or any(not isinstance(cell,str) or len(cell)>2000 for cell in row) for row in rows): return HttpResponseBadRequest("Invalid table content")
        page.content=data["content"]
    page.save(); return JsonResponse({"ok":True,"updated_at":page.updated_at.isoformat()})

@login_required
@require_POST
def toggle_favorite(request,page_id):
    workspace=_workspace(request.user); page=get_object_or_404(Page,id=page_id,workspace=workspace)
    page.is_favorite=not page.is_favorite; page.save(update_fields=["is_favorite","updated_at"])
    return JsonResponse({"favorite":page.is_favorite})

@login_required
def search(request):
    workspace=_workspace(request.user); query=request.GET.get("q","").strip()[:100]
    results=workspace.pages.filter(is_archived=False).filter(Q(title__icontains=query)|Q(content__icontains=query))[:20] if query else []
    return JsonResponse({"results":[{"id":str(p.id),"title":p.title,"icon":p.icon,"url":f"/page/{p.id}/"} for p in results]})

@login_required
@require_http_methods(["GET","POST"])
def import_notion(request):
    workspace=_workspace(request.user)
    if request.method=="GET": return render(request,"pages/import.html",{"workspace":workspace,"page_tree":_page_navigation(workspace)})
    upload=request.FILES.get("export")
    if not upload: messages.error(request,"Choose a Notion HTML file or ZIP export."); return redirect("import_notion")
    try:
        if upload.size>MAX_BYTES: raise ValueError("The export must be smaller than 1 GB.")
        imported,assets=import_notion_export(upload,workspace,request.user)
    except Exception as exc:
        messages.error(request,str(exc)); return redirect("import_notion")
    messages.success(request,f"Imported or updated {imported} pages and preserved {assets} files.")
    return redirect("home")
