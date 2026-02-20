from django import forms
from .models import Participant, Subject


class ParticipantRegistrationForm(forms.ModelForm):
    """Registration form for event participants."""

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Введите пароль",
                "required": True,
            }
        ),
        label="Пароль",
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Подтвердите пароль",
                "required": True,
            }
        ),
        label="Подтвердите пароль",
    )

    class Meta:
        model = Participant
        fields = [
            "fullname",
            "phone_number",
            "region",
            "district",
            "school",
            "grade",
            "teacher_fullname",
            "test_language",
        ]
        widgets = {
            "fullname": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Введите ваше ФИО",
                    "required": True,
                }
            ),
            "phone_number": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "+998 XX XXX XX XX",
                    "required": True,
                }
            ),
            "region": forms.Select(
                attrs={
                    "class": "form-input",
                    "required": True,
                    "id": "id_region",
                }
            ),
            "district": forms.Select(
                attrs={
                    "class": "form-input",
                    "required": True,
                    "id": "id_district",
                }
            ),
            "school": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "Название вашей школы",
                    "required": True,
                }
            ),
            "grade": forms.Select(
                attrs={
                    "class": "form-input",
                    "required": True,
                }
            ),
            "teacher_fullname": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "ФИО вашего учителя",
                    "required": True,
                }
            ),

            "test_language": forms.Select(
                attrs={
                    "class": "form-input",
                    "required": True,
                }
            ),
        }

    def clean_phone_number(self):
        """Validate and format phone number with +998 prefix."""
        phone = self.cleaned_data.get("phone_number", "")

        # Remove all non-digit characters
        digits = "".join(filter(str.isdigit, phone))

        # Remove leading 998 if present (user might have entered it)
        if digits.startswith("998"):
            digits = digits[3:]

        # Should be 9 digits (without country code)
        if len(digits) != 9:
            raise forms.ValidationError("Введите 9 цифр номера телефона (без +998)")

        # Format the phone number
        formatted_phone = f"+998{digits}"

        # Check for duplicate (excluding current instance for edit scenarios)
        existing = Participant.objects.filter(phone_number=formatted_phone)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("Этот номер телефона уже зарегистрирован")

        return formatted_phone

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Пароли не совпадают")

        return cleaned_data

    def save(self, commit=True):
        participant = super().save(commit=False)
        # Use phone_number as username
        participant.username = participant.phone_number
        participant.set_password(self.cleaned_data["password"])
        if commit:
            participant.save()
        return participant


class LoginForm(forms.Form):
    """Login form for participants."""

    phone_number = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Введите номер телефона",
                "required": True,
            }
        ),
        label="Номер телефона",
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "placeholder": "Введите пароль",
                "required": True,
            }
        ),
        label="Пароль",
    )

    def clean_phone_number(self):
        """Validate and format phone number with +998 prefix."""
        phone = self.cleaned_data.get("phone_number", "")

        # Remove all non-digit characters
        digits = "".join(filter(str.isdigit, phone))

        # Remove leading 998 if present
        if digits.startswith("998"):
            digits = digits[3:]

        # Should be 9 digits (without country code)
        if len(digits) != 9:
            raise forms.ValidationError("Введите 9 цифр номера телефона")

        return f"+998{digits}"
