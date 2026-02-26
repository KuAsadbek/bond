from django.contrib import admin
from django.db.models import Count
from .models import Participant, Subject, OlympiadSettings, Order, Achievement, AchievementImage, GuideVideo, Partner, ContactMessage

@admin.register(OlympiadSettings)
class OlympiadSettingsAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'event_date', 'location', 'is_active', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['event_name', 'location', 'address']
    readonly_fields = ['created_at', 'updated_at']
    
    

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'olympiad', 'ticket_price']
    list_filter = ['olympiad']
    search_fields = ['name']

@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ['username', 'fullname', 'phone_number', 'school', 'grade', 'test_language', 'is_paid', 'is_checked_in', 'created_at']
    list_filter = ['is_paid', 'is_checked_in', 'test_language', 'grade', 'district', 'created_at']
    search_fields = ['username', 'fullname', 'phone_number', 'school', 'teacher_fullname']
    readonly_fields = ['id', 'password', 'created_at', 'checked_in_at', 'paid_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Аккаунт', {
            'fields': ('id', 'username', 'password')
        }),
        ('Участник', {
            'fields': ('fullname', 'phone_number')
        }),
        ('Образование', {
            'fields': ('region', 'district', 'school', 'grade', 'teacher_fullname', 'test_language')
        }),
        ('Оплата', {
            'fields': ('is_paid', 'paid_at')
        }),
        ('Статус', {
            'fields': ('is_checked_in', 'checked_in_at', 'created_at')
        }),
    )
    
    def changelist_view(self, request, extra_context=None):
        """Add language statistics to the changelist view."""
        extra_context = extra_context or {}
        
        # Count participants by test language
        language_stats = Participant.objects.values('test_language').annotate(count=Count('id'))
        
        ru_count = 0
        uz_count = 0
        for stat in language_stats:
            if stat['test_language'] == 'ru':
                ru_count = stat['count']
            elif stat['test_language'] == 'uz':
                uz_count = stat['count']
        
        extra_context['ru_count'] = ru_count
        extra_context['uz_count'] = uz_count
        extra_context['total_count'] = ru_count + uz_count
        
        return super().changelist_view(request, extra_context=extra_context)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # Что показывать в списке
    list_display = (
        "id",
        "participant",
        "total_amount",
        "status",
        "payme_transaction_id",
        "payme_state",
        "payme_create_time",
        "created_at",
        "updated_at",
    )

    # Фильтры справа
    list_filter = (
        "status",
        "created_at",
    )

    # Поиск сверху (можешь добавить свои поля Participant при необходимости)
    search_fields = (
        "id",
        "participant__fullname",
        "participant__id",
        "payme_transaction_id",
    )

    # Удобная навигация по дате
    date_hierarchy = "created_at"

    # Поля в форме редактирования
    fieldsets = (
        ("Order", {
            "fields": (
                "participant",
                "total_amount",
                "status",
                "payment_method",
            )
        }),
        ("Payme", {
            "fields": (
                "payme_transaction_id",
                "payme_state",
                "payme_create_time",
                "payme_perform_time",
                "payme_cancel_time",
                "payme_cancel_reason",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    # created_at/updated_at только для чтения (иначе админка даст менять вручную)
    readonly_fields = ("created_at", "updated_at")

    # Быстрые массовые операции
    actions = (
        "mark_pending",
        "mark_paid",
        "mark_cancelled",
        "reset_payme_fields",
    )

    # Чтобы большие таблицы не тормозили: подтягиваем FK одним запросом
    list_select_related = ("participant",)

    # ---- Actions ----
    @admin.action(description="Mark as PENDING (status=pending)")
    def mark_pending(self, request, queryset):
        updated = queryset.update(status="pending")
        self.message_user(request, f"Updated: {updated}")

    @admin.action(description="Mark as PAID (status=paid) + set Payme state=2")
    def mark_paid(self, request, queryset):
        now_ms = int(timezone.now().timestamp() * 1000)
        updated = queryset.update(
            status="paid",
            payme_state=2,
            payme_perform_time=now_ms,
        )
        self.message_user(request, f"Updated: {updated}")

    @admin.action(description="Mark as CANCELLED (status=cancelled) + set Payme state=-1")
    def mark_cancelled(self, request, queryset):
        now_ms = int(timezone.now().timestamp() * 1000)
        updated = queryset.update(
            status="cancelled",
            payme_state=-1,
            payme_cancel_time=now_ms,
        )
        self.message_user(request, f"Updated: {updated}")

    @admin.action(description="Reset Payme fields (transaction/state/time/reason)")
    def reset_payme_fields(self, request, queryset):
        updated = queryset.update(
            payme_transaction_id=None,
            payme_create_time=None,
            payme_perform_time=None,
            payme_cancel_time=None,
            payme_state=None,
            payme_cancel_reason=None,
        )
        self.message_user(request, f"Reset Payme fields for: {updated} order(s)")


class AchievementImageInline(admin.TabularInline):
    model = AchievementImage
    extra = 1
    fields = ("image", "order")


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("title", "date_text", "duration", "order", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "subtitle", "date_text", "technologies")
    list_editable = ("order", "is_active")
    inlines = [AchievementImageInline]
    
@admin.register(GuideVideo)
class GuideVideoAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "description")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name",)
    list_editable = ("order", "is_active")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("name", "phone", "message")
    readonly_fields = ("created_at",)