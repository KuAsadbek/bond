from django import forms
from .models import Participant, Subject, School


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
    
    # Field for selecting school from list
    school_select = forms.ModelChoiceField(
        queryset=School.objects.all(),
        required=False,
        empty_label="Выберите школу / Maktabni tanlang",
        widget=forms.Select(
            attrs={
                "class": "form-input",
                "id": "id_school_select",
            }
        ),
        label="Выберите школу",
    )
    
    # Field for manual school entry
    school_manual = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Или введите название школы",
                "id": "id_school_manual",
            }
        ),
        label="Или введите название школы",
    )

    class Meta:
        model = Participant
        fields = [
            "fullname",
            "phone_number",
            "region",
            "district",
            "grade",
            "teacher_fullname",
            "subject",
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
            "subject": forms.Select(
                attrs={
                    "class": "form-input",
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
        school_select = cleaned_data.get("school_select")
        school_manual = cleaned_data.get("school_manual", "").strip()

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Пароли не совпадают")
        
        # Validate school selection - at least one must be provided
        if not school_select and not school_manual:
            raise forms.ValidationError("Выберите школу из списка или введите название вручную")

        return cleaned_data

    def save(self, commit=True):
        participant = super().save(commit=False)
        # Use phone_number as username
        participant.username = participant.phone_number
        
        # Set school from selection or manual entry
        school_select = self.cleaned_data.get("school_select")
        school_manual = self.cleaned_data.get("school_manual", "").strip()
        
        if school_select:
            participant.school = school_select.name
        elif school_manual:
            participant.school = school_manual
        
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
