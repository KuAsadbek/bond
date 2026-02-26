import os
import django
from datetime import datetime, timezone as tz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.public.models import Participant, Order, OlympiadSettings
from django.db.models import Q

def run():
    cutoff_date = datetime(2026, 2, 12, 0, 0, 0, tzinfo=tz.utc)
    recent = Participant.objects.filter(created_at__gte=cutoff_date)
    print(f'Total recent participants: {recent.count()}')

    p_with_orders = Participant.objects.filter(orders__isnull=False, created_at__gte=cutoff_date).distinct().count()
    p_without_orders = Participant.objects.filter(orders__isnull=True, created_at__gte=cutoff_date).count()
    print(f'Recent participants with orders: {p_with_orders}')
    print(f'Recent participants without orders: {p_without_orders}')

    olympiads = OlympiadSettings.objects.all()
    all_groups_pks = []
    
    for o in olympiads:
        print(f'\nOlympiad: {o.event_name}')
        is_preschool = "bog'cha" in o.event_name.lower() or "maktabgacha" in o.event_name.lower()
        all_orders = Order.objects.filter(olympiad=o)
        registered_ids = set(all_orders.values_list('participant_id', flat=True).distinct())
        
        if is_preschool and "maktabgacha" in o.event_name.lower():
            all_participants = recent.filter(id__in=registered_ids)
            print('Logic: Registered with orders')
        else:
            if is_preschool:
                age_group_filter = Q(grade=0)
            else:
                age_group_filter = Q(grade__in=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
            all_participants = recent.filter(age_group_filter)
            print(f'Logic: Age group filter')
        
        paid_ids = set(all_orders.filter(status='paid').values_list('participant_id', flat=True).distinct())
        paid_in_group = all_participants.filter(id__in=paid_ids)
        
        print(f'Total in group: {all_participants.count()}')
        print(f'Paid in group (Ishtirokchilar): {paid_in_group.count()}')
        print(f'Unpaid (Kutmoqda): {all_participants.count() - paid_in_group.count()}')
        
        all_groups_pks.extend(list(all_participants.values_list('id', flat=True)))

    from collections import Counter
    counts = Counter(all_groups_pks)
    overlaps = {pk: count for pk, count in counts.items() if count > 1}
    print(f'\nParticipants in multiple groups: {len(overlaps)}')
    for pk, count in list(overlaps.items())[:5]:
        p = Participant.objects.get(pk=pk)
        print(f' - Participant {p.fullname} (ID: {p.id}, Grade: {p.grade}) is in {count} groups')

if __name__ == '__main__':
    run()
