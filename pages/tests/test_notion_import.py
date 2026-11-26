import io
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from pages.models import Membership, Page, Workspace


def make_nested_notion_export():
    export = io.BytesIO()
    with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "Root.html",
            """<!doctype html><html><head><title>Root page</title></head><body>
            <p>Root page text</p>
            <a href="Child.html" data-notion-page-id="child-id">Child page</a>
            </body></html>""",
        )
        archive.writestr(
            "Child.html",
            """<!doctype html><html><head><title>Child page</title></head><body>
            <p>Child page text</p>
            <a href="Grandchild.html" data-notion-page-id="grandchild-id">Grandchild page</a>
            </body></html>""",
        )
        archive.writestr(
            "Grandchild.html",
            """<!doctype html><html><head><title>Grandchild page</title></head><body>
            <p>Grandchild page text</p>
            </body></html>""",
        )
    return export.getvalue()


class NotionImportFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="notion-user",
            password="notion-test-password",
        )
        self.workspace = Workspace.objects.create(
            name="Notion workspace",
            slug="notion-workspace",
            owner=self.user,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="owner",
        )
        self.client.force_login(self.user)
        self.export_bytes = make_nested_notion_export()

    def _preview_export(self):
        return self.client.post(
            reverse("import_notion"),
            {
                "action": "preview",
                "export": SimpleUploadedFile(
                    "notion-export.zip",
                    self.export_bytes,
                    content_type="application/zip",
                ),
            },
        )

    def test_cancel_preview_does_not_import_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with override_settings(BASE_DIR=temp_path, MEDIA_ROOT=temp_path / "media"):
                preview_response = self._preview_export()

                self.assertEqual(preview_response.status_code, 302)
                self.assertEqual(Page.objects.filter(workspace=self.workspace).count(), 0)
                preview = self.client.session["notion_import_preview"]
                staged_file = temp_path / "work" / "notion_import_previews" / f"{preview['token']}.upload"
                self.assertTrue(staged_file.exists())

                cancel_response = self.client.post(
                    reverse("import_notion"),
                    {"action": "cancel", "preview_token": preview["token"]},
                )

                self.assertEqual(cancel_response.status_code, 302)
                self.assertEqual(Page.objects.filter(workspace=self.workspace).count(), 0)
                self.assertFalse(staged_file.exists())

    def test_confirmation_imports_nested_pages_and_repeat_import_updates_them(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with override_settings(BASE_DIR=temp_path, MEDIA_ROOT=temp_path / "media"):
                self._preview_export()
                first_preview = self.client.session["notion_import_preview"]
                self.assertEqual(len(first_preview["pages"]), 3)
                self.assertTrue(all(page["status"] == "add" for page in first_preview["pages"]))

                first_import = self.client.post(
                    reverse("import_notion"),
                    {"action": "confirm", "preview_token": first_preview["token"]},
                )

                self.assertEqual(first_import.status_code, 302)
                self.assertEqual(Page.objects.filter(workspace=self.workspace).count(), 3)
                root = Page.objects.get(workspace=self.workspace, title="Root page")
                child = Page.objects.get(workspace=self.workspace, title="Child page")
                grandchild = Page.objects.get(workspace=self.workspace, title="Grandchild page")
                self.assertEqual(child.parent, root)
                self.assertEqual(grandchild.parent, child)
                self.assertIn(
                    {"type": "page_link", "text": "Child page", "url": f"/page/{child.id}/"},
                    root.content,
                )

                self._preview_export()
                repeat_preview = self.client.session["notion_import_preview"]
                self.assertTrue(all(page["status"] == "update" for page in repeat_preview["pages"]))
                repeat_import = self.client.post(
                    reverse("import_notion"),
                    {"action": "confirm", "preview_token": repeat_preview["token"]},
                )

                self.assertEqual(repeat_import.status_code, 302)
                self.assertEqual(Page.objects.filter(workspace=self.workspace).count(), 3)
                child.refresh_from_db()
                grandchild.refresh_from_db()
                self.assertEqual(child.parent, root)
                self.assertEqual(grandchild.parent, child)
