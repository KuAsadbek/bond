"""
Временный скрипт для создания тестового заказа для Payme
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.public.models import Order, Participant, OlympiadSettings
from decimal import Decimal

# Проверяем существующие заказы
print("=== Existing Orders ===")
orders = Order.objects.all()[:10]
for order in orders:
    print(f"Order #{order.id}: {order.participant.fullname} - {order.total_amount} сум - {order.status}")

print(f"\nTotal orders: {Order.objects.count()}")

# Проверяем заказ с ID 1000
existing_order = Order.objects.filter(id=1000).first()
if existing_order:
    print(f"\n✓ Order #1000 already exists:")
    print(f"  Participant: {existing_order.participant.fullname}")
    print(f"  Amount: {existing_order.total_amount} сум")
    print(f"  Status: {existing_order.status}")
else:
    print("\n✗ Order #1000 does not exist")
    
    # Получаем первого участника или создаем тестового
    participant = Participant.objects.first()
    if not participant:
        print("Creating test participant...")
        participant = Participant.objects.create(
            fullname="Test User for Payme",
            phone="+998901234567",
            school="Test School",
            grade=11,
            is_paid=False
        )
        print(f"Created participant: {participant.fullname}")
    else:
        print(f"Using existing participant: {participant.fullname}")
    
    # Получаем цену билета из настроек
    olympiad = OlympiadSettings.get_active()
    if olympiad and olympiad.ticket_price > 0:
        amount = olympiad.ticket_price
    else:
        amount = Decimal("10.00")  # 10 сум = 1000 тийинов
    
    print(f"\nCreating order #1000 with amount: {amount} сум ({int(amount * 100)} tiyin)")
    
    # Создаем заказ с конкретным ID
    # Сначала удаляем если существует
    Order.objects.filter(id=1000).delete()
    
    # Создаем новый
    order = Order(
        id=1000,
        participant=participant,
        total_amount=amount,
        status='pending',
        payment_method='payme'
    )
    order.save()
    
    print(f"✓ Created Order #{order.id}")
    print(f"  Participant: {order.participant.fullname}")
    print(f"  Amount: {order.total_amount} сум")
    print(f"  Status: {order.status}")

print("\n=== Done ===")
