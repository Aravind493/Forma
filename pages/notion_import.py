"""Import Notion's HTML, Markdown, CSV, and their linked ZIP assets."""
import csv
import hashlib
import html
import io
import posixpath
import re
import shutil
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from django.conf import settings
from django.utils.text import get_valid_filename
from .models import Page

MAX_BYTES = 1024 * 1024 * 1024
MAX_PAGES = 500

def _key(path):
    return posixpath.normpath(path.replace("\\", "/")).lstrip("./").casefold()

def _target(source, url):
    parsed=urlsplit(html.unescape(url.strip()))
    if parsed.scheme or parsed.netloc or not parsed.path: return None
    path=unquote(parsed.path).replace("\\", "/")
    return _key(posixpath.join(posixpath.dirname(source), path))

def _local_title(name):
    title=PurePosixPath(name).stem
    title=re.sub(r"\s+[0-9a-f]{32}$", "", title, flags=re.I)
    return title.replace("-", " ").strip() or "Imported page"

class NotionHTML(HTMLParser):
    """Turn exported HTML into escaped text blocks and collect local links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks=[]; self.parts=[]; self.kind="paragraph"; self.skip=0; self.title=""
        self.links=[]; self.table=None; self.row=None; self.cell=None; self.ordered=False; self.todo=False; self.containers=[]
    def _flush(self):
        text="".join(self.parts).strip(); self.parts=[]
        if text:
            block={"type":self.kind,"text":text[:20000]}
            if self.kind=="to_do": block["checked"]=self.todo
            self.blocks.append(block)
        self.todo=False
        self.kind="callout" if any(self.containers) else "paragraph"
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ("script","style","noscript"): self.skip+=1; return
        if self.skip: return
        if self.table is not None:
            if tag=="tr": self.row=[]
            elif tag in ("td","th"): self.cell=[]
            return
        if tag in ("div","aside"):
            is_callout=tag=="aside" or "callout" in attrs.get("class","").split()
            self.containers.append(is_callout)
            if is_callout: self._flush(); self.kind="callout"
        if tag=="title": self.kind="__title__"
        elif tag in ("h1","h2","h3","h4","h5","h6"):
            self._flush(); self.kind=f"heading_{min(int(tag[1]),3)}"
        elif tag in ("p","div","li","blockquote","pre","summary","aside"):
            self._flush()
            self.kind="callout" if any(self.containers) else {"li":"numbered_list" if self.ordered else "bulleted_list","blockquote":"quote","pre":"code","summary":"toggle","aside":"callout"}.get(tag,"paragraph")
        elif tag=="ol": self.ordered=True
        elif tag=="ul": self.ordered=False
        elif tag=="br": self.parts.append("\n")
        elif tag=="hr": self._flush(); self.blocks.append({"type":"divider","text":""})
        elif tag=="input" and attrs.get("type")=="checkbox": self.kind="to_do"; self.todo=bool(attrs.get("checked"))
        elif tag=="table": self._flush(); self.table=[]
        elif tag=="img":
            self._flush(); src=attrs.get("src","")
            if src: self.blocks.append({"type":"image","text":attrs.get("alt","")[:500],"url":src[:4000]})
        elif tag=="a":
            self._flush(); self.anchor={"url":attrs.get("href",""),"page_id":attrs.get("data-notion-page-id","")}; self.anchor_parts=[]
    def handle_endtag(self,tag):
        if tag in ("script","style","noscript") and self.skip: self.skip-=1; return
        if self.skip: return
        if self.table is not None:
            if tag in ("td","th") and self.cell is not None:
                self.row.append("".join(self.cell).strip()); self.cell=None
            elif tag=="tr" and self.row is not None:
                if self.row: self.table.append(self.row)
                self.row=None
            elif tag=="table":
                rows=self.table; self.table=None
                if rows: self.blocks.append({"type":"table","text":"","rows":rows[:2000]})
            return
        if tag=="title": self.title="".join(self.parts).strip(); self.parts=[]; self.kind="paragraph"
        elif tag=="a" and hasattr(self,"anchor"):
            label="".join(self.anchor_parts or self.parts).strip(); attrs=self.anchor
            self.parts=[]; self.kind="paragraph"; del self.anchor; del self.anchor_parts
            if label and attrs["url"]:
                link={"text":label[:20000],"url":attrs["url"][:4000],"page_id":attrs["page_id"]}
                self.links.append(link)
                self.blocks.append({"type":"link","text":link["text"],"url":link["url"],"notion_page_id":link["page_id"]})
        elif tag in ("h1","h2","h3","h4","h5","h6","p","div","li","blockquote","pre","summary","aside"):
            self._flush()
            if tag in ("div","aside") and self.containers:
                self.containers.pop(); self.kind="callout" if any(self.containers) else "paragraph"
        elif tag in ("ol","ul"): self.ordered=False
    def handle_data(self,data):
        if self.skip: return
        if self.cell is not None: self.cell.append(data)
        elif hasattr(self,"anchor_parts"): self.anchor_parts.append(data)
        else: self.parts.append(data)

def _parse_html(blob):
    parser=NotionHTML(); parser.feed(blob.decode("utf-8-sig",errors="replace")); parser._flush()
    return parser.title,parser.blocks

def _parse_markdown(blob):
    text=blob.decode("utf-8-sig",errors="replace"); title=""; blocks=[]; paragraph=[]; code=[]; table=[]
    def flush_paragraph():
        if not paragraph: return
        value=" ".join(x.strip() for x in paragraph).strip(); paragraph.clear(); cursor=0
        pattern=re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
        for match in pattern.finditer(value):
            before=value[cursor:match.start()].strip()
            if before: blocks.append({"type":"paragraph","text":before[:20000]})
            blocks.append({"type":"image" if match.group(1) else "link","text":match.group(2)[:20000],"url":match.group(3)[:4000]})
            cursor=match.end()
        tail=value[cursor:].strip()
        if tail: blocks.append({"type":"paragraph","text":tail[:20000]})
    in_code=False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            flush_paragraph()
            if in_code: blocks.append({"type":"code","text":"\n".join(code)[:20000]}); code=[]; in_code=False
            else: in_code=True
            continue
        if in_code: code.append(line); continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            flush_paragraph(); cells=[cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?",cell) for cell in cells): continue
            table.append(cells); continue
        if table:
            blocks.append({"type":"table","text":"","rows":table[:2000]}); table=[]
        if not line.strip(): flush_paragraph(); continue
        heading=re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$",line)
        if heading:
            flush_paragraph(); level=min(len(heading.group(1)),3); value=heading.group(2).strip()
            if not title: title=value
            blocks.append({"type":f"heading_{level}","text":value[:20000]}); continue
        task=re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.*)$",line)
        item=re.match(r"^\s*[-*+]\s+(.*)$",line)
        number=re.match(r"^\s*\d+[.)]\s+(.*)$",line)
        if task: flush_paragraph(); blocks.append({"type":"to_do","text":task.group(2)[:20000],"checked":task.group(1).lower()=="x"}); continue
        if item: flush_paragraph(); blocks.append({"type":"bulleted_list","text":item.group(1)[:20000]}); continue
        if number: flush_paragraph(); blocks.append({"type":"numbered_list","text":number.group(1)[:20000]}); continue
        if line.lstrip().startswith(">"):
            flush_paragraph(); blocks.append({"type":"quote","text":line.lstrip()[1:].strip()[:20000]}); continue
        paragraph.append(line)
    flush_paragraph()
    if code: blocks.append({"type":"code","text":"\n".join(code)[:20000]})
    if table: blocks.append({"type":"table","text":"","rows":table[:2000]})
    return title,blocks

def _parse_csv(blob):
    if hasattr(blob,"read"):
        stream=io.TextIOWrapper(blob,encoding="utf-8-sig",errors="replace",newline="")
        reader=csv.reader(stream)
    else: reader=csv.reader(io.StringIO(blob.decode("utf-8-sig",errors="replace")))
    rows=[row for _,row in zip(range(2000),reader)]
    if hasattr(blob,"read"): stream.detach()
    return [{"type":"table","text":"","rows":rows}] if rows else []

def _source_id(name):
    match=re.search(r"([0-9a-f]{32})$",PurePosixPath(name).stem,re.I)
    return match.group(1).lower() if match else hashlib.sha256(_key(name).encode("utf-8")).hexdigest()

def _store_asset(archive,name,workspace):
    base=get_valid_filename(PurePosixPath(name).name)[:120] or "attachment"
    digest=hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    relative=f"notion/{workspace.pk}/{digest}_{base}"
    target=Path(settings.MEDIA_ROOT)/"notion"/str(workspace.pk)/f"{digest}_{base}"
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with archive.open(name) as src, target.open("wb") as dst: shutil.copyfileobj(src,dst,1024*1024)
    return "/media/"+quote(relative,safe="/")

def _store_upload(upload,workspace):
    base=get_valid_filename(PurePosixPath(upload.name).name)[:120] or "attachment"
    digest=hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks(): digest.update(chunk)
    upload.seek(0); token=digest.hexdigest()[:16]
    relative=f"notion/{workspace.pk}/{token}_{base}"
    target=Path(settings.MEDIA_ROOT)/"notion"/str(workspace.pk)/f"{token}_{base}"
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with target.open("wb") as dst:
            for chunk in upload.chunks(): dst.write(chunk)
    upload.seek(0)
    return "/media/"+quote(relative,safe="/")

def _resolve_url(source,url,page_keys,asset_urls):
    key=_target(source,url)
    if key in page_keys and key!=_key(source): return ("page",page_keys[key])
    if key in asset_urls: return ("file",asset_urls[key])
    parsed=urlsplit(url)
    if parsed.scheme.lower() in ("https","http","mailto"): return ("link",url)
    return ("text",url)

def _plain_html_page(upload,workspace,user):
    title,blocks=_parse_html(upload.read()); title=title or PurePosixPath(upload.name).stem or "Imported page"
    page=Page.objects.create(workspace=workspace,created_by=user,title=title[:300],source_id=_source_id(upload.name),content=blocks or [{"type":"paragraph","text":"Imported from Notion."}])
    return 1,0

def import_notion_export(upload,workspace,user):
    """Import an HTML page or a Notion ZIP, updating matching pages on re-import."""
    upload.seek(0)
    if not zipfile.is_zipfile(upload):
        upload.seek(0)
        suffix=PurePosixPath(upload.name).suffix.lower()
        if suffix in (".html",".htm"): return _plain_html_page(upload,workspace,user)
        if suffix in (".md",".markdown"):
            file_url=_store_upload(upload,workspace); title,blocks=_parse_markdown(upload.read()); title=title or PurePosixPath(upload.name).stem
            blocks.append({"type":"file","text":"Download original Markdown","url":file_url})
            Page.objects.create(workspace=workspace,created_by=user,title=title[:300],source_id=_source_id(upload.name),content=blocks)
            return 1,0
        if suffix==".csv":
            file_url=_store_upload(upload,workspace); rows=_parse_csv(upload); title=PurePosixPath(upload.name).stem
            rows.append({"type":"file","text":"Download full CSV","url":file_url})
            Page.objects.create(workspace=workspace,created_by=user,title=title[:300],source_id=_source_id(upload.name),content=rows)
            return 1,0
        raise ValueError("Choose a Notion ZIP, HTML, Markdown, or CSV file.")
    upload.seek(0)
    with zipfile.ZipFile(upload) as archive:
        names=[info.filename for info in archive.infolist() if not info.is_dir() and not info.filename.startswith("__MACOSX/")]
        if sum(archive.getinfo(n).file_size for n in names)>MAX_BYTES: raise ValueError("Uncompressed export content exceeds 1 GB.")
        html_names=[n for n in names if PurePosixPath(n).suffix.lower() in (".html",".htm")]
        html_data={_key(n):_parse_html(archive.read(n)) for n in html_names}
        referenced_md=set()
        for name in html_names:
            parser=NotionHTML(); parser.feed(archive.read(name).decode("utf-8-sig",errors="replace"))
            for link in parser.links:
                key=_target(name,link.get("url", ""))
                if key and key.endswith((".md",".markdown")): referenced_md.add(key)
        page_names=html_names+[n for n in names if PurePosixPath(n).suffix.lower() in (".md",".markdown") and _key(n) not in referenced_md]+[n for n in names if PurePosixPath(n).suffix.lower()==".csv"]
        if len(page_names)>MAX_PAGES: raise ValueError("The export contains more than 500 HTML, Markdown, and CSV pages.")
        page_keys={_key(n):n for n in page_names}
        asset_names=[n for n in names if n not in page_names]
        asset_urls={_key(n):_store_asset(archive,n,workspace) for n in asset_names}
        objects={}; blocks_by_key={}; parents={}; count=0
        for name in page_names:
            key=_key(name); suffix=PurePosixPath(name).suffix.lower()
            if suffix in (".html",".htm"):
                data=archive.read(name)
                title,blocks=html_data[key]
                title=title or _local_title(name)
                # Notion's child-page blocks carry data-notion-page-id; those links define the real tree even in a flat ZIP.
                parser=NotionHTML(); parser.feed(data.decode("utf-8-sig",errors="replace"))
                for link in parser.links:
                    target=_target(name,link.get("url",""))
                    if link.get("page_id") and target in page_keys and target!=key and target not in parents: parents[target]=key
            elif suffix in (".md",".markdown"):
                data=archive.read(name)
                title,blocks=_parse_markdown(data); title=title or _local_title(name)
                for block in blocks:
                    target=_target(name,block.get("url","")) if block.get("type") in {"link","image"} else None
                    if block.get("type")=="link" and target in page_keys and target!=key and target not in parents: parents[target]=key
            else:
                title=PurePosixPath(name).stem; blocks=_parse_csv(archive.open(name))
            blocks_by_key[key]=blocks
            source_id=_source_id(name)
            page=Page.objects.filter(workspace=workspace,source_id=source_id).first()
            if page is None:
                # Adopt pages from the earlier flat importer so a corrected re-import repairs them instead of duplicating them.
                page=Page.objects.filter(workspace=workspace,created_by=user,parent__isnull=True,source_id="",title__iexact=title[:300]).first()
            if page is None: page=Page(workspace=workspace,created_by=user)
            page.title=title[:300]; page.source_id=source_id; page.content=blocks or [{"type":"paragraph","text":"Imported from Notion."}]
            page.save(); objects[key]=page; count+=1
        # Notion's optional folder layout is another hierarchy source for Markdown/HTML exports.
        for child_key,name in page_keys.items():
            if child_key in parents: continue
            directory=PurePosixPath(name).parent
            while str(directory) not in (".",""):
                parent_base=directory.name
                for extension in (".html",".htm",".md",".markdown"):
                    candidate=_key(str(directory.parent/(parent_base+extension)))
                    if candidate in page_keys and candidate!=child_key:
                        parents[child_key]=candidate; break
                if child_key in parents: break
                directory=directory.parent
        # Resolve actual file assets and page links now that every page has a database ID.
        for key,page in objects.items():
            source=page_keys[key]; cleaned=[]
            for block in blocks_by_key[key]:
                item=dict(block); kind=item.get("type")
                if kind=="image":
                    resolved=_resolve_url(source,item.get("url",""),objects,asset_urls)
                    if resolved[0]=="file": item["url"]=resolved[1]
                    elif resolved[0]=="link": item["url"]=resolved[1]
                    else: item["url"]=""
                elif kind=="link":
                    resolved=_resolve_url(source,item.get("url",""),objects,asset_urls)
                    if resolved[0]=="page": item={"type":"page_link","text":item.get("text",""),"url":f"/page/{resolved[1].id}/"}
                    elif resolved[0]=="file": item={"type":"file","text":item.get("text") or PurePosixPath(urlsplit(block.get("url","")).path).name,"url":resolved[1]}
                    elif resolved[0]=="link": item={"type":"link","text":item.get("text",""),"url":resolved[1]}
                    else: item={"type":"paragraph","text":item.get("text","")}
                cleaned.append(item)
            if PurePosixPath(source).suffix.lower() in (".md",".markdown",".csv"):
                source_url=_store_asset(archive,source,workspace)
                label="Download full CSV" if source.lower().endswith(".csv") else "Download original Markdown"
                cleaned.append({"type":"file","text":label,"url":source_url})
            page.content=cleaned or [{"type":"paragraph","text":"Imported from Notion."}]
            page.parent=objects.get(parents.get(key))
            page.save(update_fields=["content","parent","updated_at"])
        return count,len(asset_urls)
