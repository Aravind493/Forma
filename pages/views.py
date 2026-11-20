import json
import uuid
from copy import deepcopy
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
    pages_by_id={page.id:page for page in pages}
    for parent_id, child_pages in children.items():
        parent=pages_by_id[parent_id]
        block_order={
            block.get("url"): position
            for position, block in enumerate(parent.content if isinstance(parent.content,list) else [])
            if isinstance(block,dict) and block.get("type")=="page_link"
        }
        child_pages.sort(
            key=lambda child: (
                block_order.get(f"/page/{child.id}/", len(block_order)),
                child.created_at,
                child.title,
            )
        )
    parent_ids={page.parent_id for page in pages if page.parent_id in ids}
    result=[]; visited=set()
    def add(page,depth):
        if page.id in visited: return
        visited.add(page.id); result.append({"page":page,"level":depth,"indent":depth*14,"has_children":page.id in parent_ids})
        for child in children[page.id]: add(child,depth+1)
    for root in roots: add(root,0)
    for page in pages: add(page,0)
    return result

def _page_sidebar_context(workspace,user):
    active=workspace.pages.filter(is_archived=False)
    archived_roots=workspace.pages.filter(is_archived=True).filter(
        Q(parent__isnull=True)|Q(parent__is_archived=False)
    ).order_by("-updated_at","title")
    membership=Membership.objects.filter(workspace=workspace,user=user).only("role").first()
    return {
        "page_tree":_page_navigation(workspace),
        "favorite_pages":active.filter(is_favorite=True).order_by("title")[:8],
        "recent_pages":active.order_by("-updated_at","title")[:8],
        "archived_pages":archived_roots[:30],
        "can_edit_pages":bool(membership and membership.role!="viewer"),
    }

def _page_subtree_ids(page):
    ids=[page.pk]
    pending=[page.pk]
    while pending:
        child_ids=list(Page.objects.filter(workspace_id=page.workspace_id,parent_id__in=pending).values_list("id",flat=True))
        pending=child_ids
        ids.extend(child_ids)
    return ids

def _remove_page_reference(parent,page_id):
    if not parent or not isinstance(parent.content,list):
        return
    page_url=f"/page/{page_id}/"
    updated=[
        block for block in parent.content
        if not (isinstance(block,dict) and block.get("type")=="page_link" and block.get("url")==page_url)
    ]
    if updated!=parent.content:
        parent.content=updated
        parent.save(update_fields=["content","updated_at"])

def _append_page_reference(parent,page):
    if not parent:
        return
    blocks=parent.content if isinstance(parent.content,list) else []
    page_url=f"/page/{page.id}/"
    existing=next((
        block for block in blocks
        if isinstance(block,dict) and block.get("type")=="page_link" and block.get("url")==page_url
    ),None)
    if existing:
        if existing.get("text")!=page.title:
            existing["text"]=page.title
            parent.content=blocks
            parent.save(update_fields=["content","updated_at"])
    else:
        blocks.append({"type":"page_link","text":page.title,"url":page_url})
        parent.content=blocks
        parent.save(update_fields=["content","updated_at"])

def _insert_page_reference_after(parent,reference_page,page):
    if not parent:
        return
    blocks=parent.content if isinstance(parent.content,list) else []
    page_url=f"/page/{page.id}/"
    if any(isinstance(block,dict) and block.get("type")=="page_link" and block.get("url")==page_url for block in blocks):
        return
    reference_url=f"/page/{reference_page.id}/"
    position=next((
        index+1 for index,block in enumerate(blocks)
        if isinstance(block,dict) and block.get("type")=="page_link" and block.get("url")==reference_url
    ),len(blocks))
    blocks.insert(position,{"type":"page_link","text":page.title,"url":page_url})
    parent.content=blocks
    parent.save(update_fields=["content","updated_at"])

def _duplicate_page_tree(source,parent,creator,title=None,mapping=None):
    if mapping is None:
        mapping={}
    duplicate=Page.objects.create(
        workspace=source.workspace,
        created_by=creator,
        parent=parent,
        title=title or source.title,
        icon=source.icon,
        content=[],
    )
    mapping[str(source.id)]=duplicate
    children=list(source.children.filter(is_archived=False).order_by("created_at","title"))
    for child in children:
        _duplicate_page_tree(child,duplicate,creator,mapping=mapping)

    content=deepcopy(source.content) if isinstance(source.content,list) else []
    linked_ids=set()
    for block in content:
        if not isinstance(block,dict) or block.get("type")!="page_link":
            continue
        old_url=block.get("url","")
        old_id=old_url.removeprefix("/page/").removesuffix("/")
        copied=mapping.get(old_id)
        if copied:
            block["url"]=f"/page/{copied.id}/"
            block["text"]=copied.title
            linked_ids.add(str(copied.id))
    for child in children:
        copied=mapping[str(child.id)]
        if str(copied.id) not in linked_ids:
            content.append({"type":"page_link","text":copied.title,"url":f"/page/{copied.id}/"})
    duplicate.content=content
    duplicate.save(update_fields=["content"])
    return duplicate

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
    context=_page_sidebar_context(workspace,request.user)
    context.update({"workspace":workspace,"page":page,"home_url":"/"})
    return render(request,"pages/editor.html",context)

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
    if data.get("parent"):
        parent=get_object_or_404(Page,id=data["parent"],workspace=workspace)
        if Membership.objects.get(workspace=workspace,user=request.user).role=="viewer":
            return JsonResponse({"error":"Read only"},status=403)
    insert_at=data.get("insert_at")
    if insert_at is not None and (isinstance(insert_at,bool) or not isinstance(insert_at,int)):
        return HttpResponseBadRequest("Invalid insertion position")
    inserted_at=None
    with transaction.atomic():
        page=Page.objects.create(workspace=workspace,created_by=request.user,parent=parent,title="Untitled",icon="📄")
        if parent:
            blocks=parent.content if isinstance(parent.content,list) else []
            page_block={"type":"page_link","text":page.title,"url":f"/page/{page.id}/"}
            if insert_at is None:
                inserted_at=len(blocks)
                blocks.append(page_block)
            else:
                position=max(0,min(insert_at,len(blocks)))
                if position<len(blocks) and isinstance(blocks[position],dict) and blocks[position].get("type")=="paragraph" and not blocks[position].get("text","").strip():
                    blocks[position]=page_block
                else:
                    blocks.insert(position,page_block)
                inserted_at=position
            parent.content=blocks
            parent.save(update_fields=["content","updated_at"])
    return JsonResponse({"id":str(page.id),"url":f"/page/{page.id}/","insert_at":inserted_at},status=201)

@login_required
@require_http_methods(["PATCH"])
def update_page(request,page_id):
    workspace=_workspace(request.user); page=get_object_or_404(Page,id=page_id,workspace=workspace)
    member=Membership.objects.get(workspace=workspace,user=request.user)
    if member.role=="viewer": return JsonResponse({"error":"Read only"},status=403)
    try: data=json.loads(request.body)
    except (ValueError,TypeError): return HttpResponseBadRequest("Invalid JSON")
    title_changed="title" in data and page.title!=str(data["title"])[:300]
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
    page.save()
    if title_changed and page.parent_id:
        parent=page.parent
        blocks=parent.content if isinstance(parent.content,list) else []
        page_url=f"/page/{page.id}/"
        changed=False
        for block in blocks:
            if isinstance(block,dict) and block.get("type")=="page_link" and block.get("url")==page_url:
                block["text"]=page.title
                changed=True
        if changed:
            parent.content=blocks
            parent.save(update_fields=["content","updated_at"])
    return JsonResponse({"ok":True,"updated_at":page.updated_at.isoformat()})

@login_required
@require_POST
def toggle_favorite(request,page_id):
    workspace=_workspace(request.user); page=get_object_or_404(Page,id=page_id,workspace=workspace)
    page.is_favorite=not page.is_favorite; page.save(update_fields=["is_favorite"])
    return JsonResponse({"favorite":page.is_favorite})

@login_required
@require_POST
def page_actions(request,page_id):
    workspace=_workspace(request.user)
    page=get_object_or_404(Page.objects.select_related("parent"),id=page_id,workspace=workspace)
    membership=Membership.objects.get(workspace=workspace,user=request.user)
    if membership.role=="viewer":
        return JsonResponse({"error":"Read only"},status=403)
    try:
        data=json.loads(request.body or "{}")
    except (ValueError,TypeError):
        return HttpResponseBadRequest("Invalid JSON")
    if not isinstance(data,dict):
        return HttpResponseBadRequest("Invalid action")

    action=data.get("action")
    if action=="move":
        parent_id=data.get("parent_id") or None
        if parent_id:
            try:
                parent_id=uuid.UUID(str(parent_id))
            except (ValueError,TypeError,AttributeError):
                return HttpResponseBadRequest("Invalid destination page")
        new_parent=get_object_or_404(Page,id=parent_id,workspace=workspace,is_archived=False) if parent_id else None
        ancestor=new_parent
        while ancestor:
            if ancestor.id==page.id:
                return JsonResponse({"error":"A page cannot be moved into itself or its own nested page."},status=400)
            ancestor=ancestor.parent
        if page.parent_id==getattr(new_parent,"id",None):
            return JsonResponse({"ok":True})
        with transaction.atomic():
            _remove_page_reference(page.parent,page.id)
            page.parent=new_parent
            page.save(update_fields=["parent","updated_at"])
            _append_page_reference(new_parent,page)
        return JsonResponse({"ok":True})

    if action=="duplicate":
        with transaction.atomic():
            duplicate=_duplicate_page_tree(page,page.parent,request.user,title=f"{page.title} (copy)"[:300])
            _insert_page_reference_after(page.parent,page,duplicate)
        return JsonResponse({"id":str(duplicate.id),"url":f"/page/{duplicate.id}/"},status=201)

    if action=="archive":
        with transaction.atomic():
            _remove_page_reference(page.parent,page.id)
            Page.objects.filter(id__in=_page_subtree_ids(page)).update(is_archived=True)
        return JsonResponse({"ok":True})

    if action=="restore":
        if not page.is_archived:
            return JsonResponse({"error":"Page is not archived"},status=400)
        with transaction.atomic():
            Page.objects.filter(id__in=_page_subtree_ids(page)).update(is_archived=False)
            page.refresh_from_db(fields=["parent","title"])
            if page.parent_id and page.parent and not page.parent.is_archived:
                _append_page_reference(page.parent,page)
        return JsonResponse({"ok":True})

    if action=="delete":
        with transaction.atomic():
            _remove_page_reference(page.parent,page.id)
            page.delete()
        return JsonResponse({"ok":True})

    return JsonResponse({"error":"Unknown page action"},status=400)

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
