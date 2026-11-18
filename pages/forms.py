from django import forms
from django.contrib.auth import get_user_model
from .models import Profile

User = get_user_model()


class AccountDetailsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name", "placeholder": "Last name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
        }


class ProfileDetailsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["job_title", "location", "website", "bio"]
        widgets = {
            "job_title": forms.TextInput(attrs={"placeholder": "e.g. Django developer"}),
            "location": forms.TextInput(attrs={"placeholder": "City, country"}),
            "website": forms.URLInput(attrs={"placeholder": "https://your-site.com", "autocomplete": "url"}),
            "bio": forms.Textarea(attrs={"rows": 4, "maxlength": 500, "placeholder": "A few words about you, your interests, or what you are working on…"}),
        }
