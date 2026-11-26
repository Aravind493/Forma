import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pages.models import Membership, Page, Workspace


class PageAccessAndAutosaveTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="owner",
            password="owner-test-password",
        )
        self.workspace = Workspace.objects.create(
            name="Owner's workspace",
            slug="owners-workspace",
            owner=self.owner,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role="owner",
        )
        self.page = Page.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            title="Draft",
            content=[{"type": "paragraph", "text": "Original text"}],
        )

    def test_autosave_persists_title_icon_and_content(self):
        self.client.force_login(self.owner)
        payload = {
            "title": "Saved title",
            "icon": "📝",
            "content": [
                {"type": "heading_1", "text": "Saved heading"},
                {"type": "paragraph", "text": "Saved paragraph"},
            ],
        }

        response = self.client.patch(
            reverse("update_page", args=[self.page.id]),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.page.refresh_from_db()
        self.assertEqual(self.page.title, "Saved title")
        self.assertEqual(self.page.icon, "📝")
        self.assertEqual(self.page.content, payload["content"])

    def test_viewer_can_read_but_cannot_autosave(self):
        viewer = get_user_model().objects.create_user(
            username="viewer",
            password="viewer-test-password",
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=viewer,
            role="viewer",
        )
        self.client.force_login(viewer)

        read_response = self.client.get(reverse("page", args=[self.page.id]))
        save_response = self.client.patch(
            reverse("update_page", args=[self.page.id]),
            data=json.dumps({"content": [{"type": "paragraph", "text": "Changed"}]}),
            content_type="application/json",
        )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(save_response.status_code, 403)
        self.page.refresh_from_db()
        self.assertEqual(self.page.content[0]["text"], "Original text")

    def test_member_cannot_open_page_from_another_workspace(self):
        other_owner = get_user_model().objects.create_user(
            username="other-owner",
            password="other-owner-test-password",
        )
        other_workspace = Workspace.objects.create(
            name="Other workspace",
            slug="other-workspace",
            owner=other_owner,
        )
        other_page = Page.objects.create(
            workspace=other_workspace,
            created_by=other_owner,
            title="Private page",
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse("page", args=[other_page.id]))

        self.assertEqual(response.status_code, 404)
