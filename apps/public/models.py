from django.db import models
from django.contrib.auth.hashers import make_password, check_password
import uuid

class Subject(models.Model):
    """Subject model for participant subject selection."""

    name = models.CharField(max_length=100, verbose_name="Название предмета")
    olympiad = models.ForeignKey(
        'OlympiadSettings',
        on_delete=models.CASCADE,
        related_name='subjects',
        verbose_name="Олимпиада",
        null=True,
        blank=True,
    )
    ticket_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Стоимость билета (сум)"
    )

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ["name"]

    def __str__(self):
        olympiad_name = self.olympiad.event_name if self.olympiad else 'Без олимпиады'
        return f"{self.name} ({olympiad_name}) - {self.ticket_price} сум"


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

    test_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default='ru',
        verbose_name="Язык теста"
    )

    # Payment fields
    is_paid = models.BooleanField(default=False, verbose_name="Оплачен")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата оплаты")

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


class PhoneVerification(models.Model):
    """Model to store phone verification codes."""

    phone_number = models.CharField(max_length=20, verbose_name="Номер телефона")
    code = models.CharField(max_length=6, verbose_name="Код подтверждения")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    is_verified = models.BooleanField(default=False, verbose_name="Подтверждён")

    class Meta:
        verbose_name = "Подтверждение телефона"
        verbose_name_plural = "Подтверждения телефонов"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phone_number} - {self.code}"

    def is_valid(self):
        """Check if verification code is still valid (5 min TTL)."""
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() - self.created_at < timedelta(minutes=5)


class OlympiadSettings(models.Model):
    """Singleton model for olympiad event settings."""

    event_name = models.CharField(
        max_length=255, 
        default="BOND Olimpiadasi", 
        verbose_name="Название мероприятия"
    )

    event_date = models.DateTimeField(
        verbose_name="Дата и время начала"
    )
    location = models.CharField(
        max_length=500, 
        verbose_name="Место проведения"
    )
    address = models.TextField(
        blank=True, 
        verbose_name="Адрес"
    )
    description = models.TextField(
        blank=True, 
        verbose_name="Описание"
    )
    is_active = models.BooleanField(
        default=True, 
        verbose_name="Активно"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Создано"
    )
    updated_at = models.DateTimeField(
        auto_now=True, 
        verbose_name="Обновлено"
    )
    illustration = models.ImageField(
        upload_to='olympiads/', 
        null=True, 
        blank=True, 
        verbose_name="Иллюстрация"
    )

    class Meta:
        verbose_name = "Настройки олимпиады"
        verbose_name_plural = "Настройки олимпиады"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_name} - {self.event_date.strftime('%d.%m.%Y %H:%M')}"

    @classmethod
    def get_active(cls):
        """Get the active olympiad settings."""
        return cls.objects.filter(is_active=True).first()


class Order(models.Model):
    """Order model for tracking payments."""

    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('paid', 'Оплачен'),
        ('cancelled', 'Отменён'),
        ('failed', 'Ошибка'),
    ]

    id = models.BigAutoField(primary_key=True)
    participant = models.ForeignKey(
        Participant, 
        on_delete=models.CASCADE, 
        related_name='orders',
        verbose_name="Участник"
    )
    olympiad = models.ForeignKey(
        'OlympiadSettings',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name="Олимпиада"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name="Предмет"
    )
    total_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        verbose_name="Сумма (сум)"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name="Статус"
    )
    payment_method = models.CharField(
        max_length=20,
        default='payme',
        verbose_name="Способ оплаты"
    )
       
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")
    
    # Payme specific fields
    payme_transaction_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        verbose_name="Payme Transaction ID"
    )
    
    payme_create_time = models.BigIntegerField(null=True, blank=True, verbose_name="Payme create_time (ms)")
    payme_perform_time = models.BigIntegerField(null=True, blank=True, verbose_name="Payme perform_time (ms)")
    payme_cancel_time = models.BigIntegerField(null=True, blank=True, verbose_name="Payme cancel_time (ms)")
    payme_state = models.IntegerField(null=True, blank=True, verbose_name="Payme state")
    payme_cancel_reason = models.IntegerField(null=True, blank=True, verbose_name="Payme cancel reason")
    
    # Click specific fields
    click_trans_id = models.BigIntegerField(null=True, blank=True, verbose_name="Click Transaction ID")
    click_prepare_id = models.BigIntegerField(null=True, blank=True, verbose_name="Click Prepare ID")

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} - {self.participant.fullname} - {self.status}"


class Achievement(models.Model):
    """Model for Hall of Fame (Shon-sharaf) achievements."""

    title = models.CharField(max_length=255, verbose_name="Заголовок")
    subtitle = models.CharField(max_length=255, verbose_name="Подзаголовок", blank=True)
    date_text = models.CharField(max_length=100, verbose_name="Текст даты (напр. ОКТЯБРЬ 2024)", blank=True)
    image = models.ImageField(upload_to='achievements/', verbose_name="Изображение")
    url = models.URLField(blank=True, verbose_name="Ссылка (необязательно)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    # Detail page fields
    description = models.TextField(blank=True, verbose_name="Описание (подробное)")
    duration = models.CharField(max_length=50, blank=True, verbose_name="Katnashuvchilar soni")
    technologies = models.CharField(max_length=500, blank=True, verbose_name="Технологии (через запятую)", help_text="Напр: Python, Next JS, React JS, Flutter")

    class Meta:
        verbose_name = "Достижение (Зал славы)"
        verbose_name_plural = "Достижения (Зал славы)"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.title

    def get_technologies_list(self):
        """Return technologies as a list."""
        if self.technologies:
            return [t.strip() for t in self.technologies.split(',') if t.strip()]
        return []


class AchievementImage(models.Model):
    """Gallery images for Achievement detail page."""

    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name='gallery_images',
        verbose_name="Достижение"
    )
    image = models.ImageField(upload_to='achievements/gallery/', verbose_name="Изображение")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")

    class Meta:
        verbose_name = "Фото галереи"
        verbose_name_plural = "Фото галереи"
        ordering = ["order"]

    def __str__(self):
        return f"Image for {self.achievement.title} #{self.order}"


class GuideVideo(models.Model):
    """Model for Guide (Qo'llanma) videos."""

    title = models.CharField(max_length=255, verbose_name="Заголовок")
    description = models.TextField(blank=True, verbose_name="Описание")
    video_file = models.FileField(upload_to='guides/videos/', verbose_name="Видео файл", blank=True, null=True)
    video_url = models.URLField(blank=True, verbose_name="Ссылка на видео (YouTube/Vimeo)", help_text="Если загружен файл, это поле игнорируется")
    thumbnail = models.ImageField(upload_to='guides/thumbnails/', verbose_name="Превью (обложка)")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Видео руководство"
        verbose_name_plural = "Видео руководства"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Partner(models.Model):
    """Model for Partners (Hamkorlarimiz)."""

    name = models.CharField(max_length=255, verbose_name="Название")
    logo = models.ImageField(upload_to='partners/', verbose_name="Логотип (светлый/прозрачный)")
    url = models.URLField(blank=True, verbose_name="Ссылка на сайт (необязательно)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Партнер"
        verbose_name_plural = "Партнеры"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name


class ContactMessage(models.Model):
    """Model for Contact Messages (Bog'lanish)."""

    name = models.CharField(max_length=255, verbose_name="Имя")
    phone = models.CharField(max_length=20, verbose_name="Телефон")
    message = models.TextField(verbose_name="Сообщение")
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Сообщение (Контакты)"
        verbose_name_plural = "Сообщения (Контакты)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.phone}"
