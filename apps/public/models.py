from django.db import models
from django.contrib.auth.hashers import make_password, check_password
import uuid


class Subject(models.Model):
    """Subject model for participant subject selection."""

    name = models.CharField(max_length=100, verbose_name="Название предмета")

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Participant(models.Model):
    """Event participant model with registration data and check-in status."""

    GRADE_CHOICES = [(i, str(i)) for i in range(1, 12)]
    LANGUAGE_CHOICES = [
        ('ru', 'Русский'),
        ('uz', "O'zbek"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Auth fields
    username = models.CharField(max_length=50, unique=True, verbose_name="Логин")
    password = models.CharField(max_length=128, verbose_name="Пароль")

    # Profile fields
    fullname = models.CharField(max_length=255, verbose_name="ФИО участника")
    phone_number = models.CharField(
        max_length=20, unique=True, verbose_name="Номер телефона"
    )
    region = models.CharField(max_length=100, verbose_name="Регион", default="")
    district = models.CharField(max_length=100, verbose_name="Район")
    school = models.CharField(max_length=255, verbose_name="Школа")
    grade = models.PositiveSmallIntegerField(
        choices=GRADE_CHOICES, verbose_name="Класс"
    )
    teacher_fullname = models.CharField(max_length=255, verbose_name="ФИО учителя")
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Предмет",
    )
    test_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default='ru',
        verbose_name="Язык теста"
    )

    is_checked_in = models.BooleanField(default=False, verbose_name="Присутствовал")
    checked_in_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Время отметки"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Дата регистрации"
    )

    # Rating score set by admin
    score = models.IntegerField(default=0, verbose_name="Балл")

    # Telegram subscription
    telegram_user_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="Telegram ID"
    )
    telegram_subscribed = models.BooleanField(
        default=False, verbose_name="Подписан на канал"
    )

    class Meta:
        verbose_name = "Участник"
        verbose_name_plural = "Участники"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.fullname} - {self.school} ({self.grade} класс)"

    def set_password(self, raw_password):
        """Hash and set the password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Check if the given password matches."""
        return check_password(raw_password, self.password)
