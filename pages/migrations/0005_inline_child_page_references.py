from django.db import migrations


def add_child_page_references(apps, schema_editor):
    Page = apps.get_model("pages", "Page")
    database = schema_editor.connection.alias

    parents = (
        Page.objects.using(database)
        .filter(children__is_archived=False)
        .distinct()
        .iterator()
    )
    for parent in parents:
        blocks = parent.content if isinstance(parent.content, list) else []
        existing_urls = {
            block.get("url")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "page_link"
        }
        changed = False

        children = (
            Page.objects.using(database)
            .filter(parent_id=parent.pk, is_archived=False)
            .order_by("created_at", "title")
        )
        for child in children:
            url = f"/page/{child.pk}/"
            if url in existing_urls:
                continue
            blocks.append({"type": "page_link", "text": child.title, "url": url})
            existing_urls.add(url)
            changed = True

        if changed:
            parent.content = blocks
            parent.save(using=database, update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0004_profile"),
    ]

    operations = [
        migrations.RunPython(add_child_page_references, migrations.RunPython.noop),
    ]
