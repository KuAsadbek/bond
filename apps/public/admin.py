from django.contrib import admin
from django.db.models import Count
from .models import Participant, Subject, School, OlympiadSettings


@admin.register(OlympiadSettings)
class OlympiadSettingsAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'event_date', 'location', 'is_active', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['event_name', 'location', 'address']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Мероприятие', {
            'fields': ('event_name', 'event_date', 'ticket_price', 'is_active')
        }),
        ('Место проведения', {
            'fields': ('location', 'address')
        }),
        ('Дополнительно', {
            'fields': ('description', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'district']
    list_filter = ['district']
    search_fields = ['name', 'district']


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ['username', 'fullname', 'phone_number', 'school', 'grade', 'subject', 'test_language', 'is_paid', 'is_checked_in', 'created_at']
    list_filter = ['is_paid', 'is_checked_in', 'test_language', 'grade', 'district', 'subject', 'created_at']
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
            'fields': ('region', 'district', 'school', 'grade', 'teacher_fullname', 'subject', 'test_language')
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
