from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pages.models import Membership, Page, Workspace


class AuthenticationFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="aravind",
            password="a-secure-test-password",
        )
        self.workspace = Workspace.objects.create(
            name="Aravind's workspace",
            slug="aravinds-workspace",
            owner=self.user,
        )
        Membership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role="owner",
        )
        self.page = Page.objects.create(
            workspace=self.workspace,
            created_by=self.user,
            title="Welcome",
        )

    def test_user_can_sign_in(self):
        response = self.client.post(
            reverse("login"),
            {"username": "aravind", "password": "a-secure-test-password"},
        )

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        page_response = self.client.get(reverse("page", args=[self.page.id]))
        self.assertEqual(page_response.status_code, 200)

    def test_page_requires_sign_in(self):
        response = self.client.get(reverse("page", args=[self.page.id]))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('page', args=[self.page.id])}",
            fetch_redirect_response=False,
        )
