from django import forms
from django.core.exceptions import ValidationError
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
    avatar = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            "accept": "image/jpeg,image/png,image/webp",
            "class": "avatar-file-input",
        }),
    )
    remove_avatar = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "avatar-remove-input"}),
    )

    class Meta:
        model = Profile
        fields = ["avatar", "job_title", "location", "website", "bio"]
        widgets = {
            "job_title": forms.TextInput(attrs={"placeholder": "e.g. Django developer"}),
            "location": forms.TextInput(attrs={"placeholder": "City, country"}),
            "website": forms.URLInput(attrs={"placeholder": "https://your-site.com", "autocomplete": "url"}),
            "bio": forms.Textarea(attrs={"rows": 4, "maxlength": 500, "placeholder": "A few words about you, your interests, or what you are working on…"}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        uploaded_avatar = self.files.get("avatar")
        if not uploaded_avatar:
            return avatar
        if not avatar or avatar is False:
            return avatar
        if avatar.size > 5 * 1024 * 1024:
            raise ValidationError("Choose an image smaller than 5 MB.")
        image = avatar.image
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("Use a JPEG, PNG, or WebP image.")
        if image.width > 4096 or image.height > 4096:
            raise ValidationError("Choose an image no larger than 4096 × 4096 pixels.")
        return avatar

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("remove_avatar") and not self.files.get("avatar"):
            cleaned_data["avatar"] = False
        return cleaned_data
