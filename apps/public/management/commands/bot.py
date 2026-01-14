import os
import io
import asyncio
from django.core.management.base import BaseCommand
from django.utils import timezone
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from PIL import Image
from pyzbar.pyzbar import decode

# Import Django models
from apps.public.models import Participant


class Command(BaseCommand):
    help = "Run the Telegram bot for participant check-in"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Telegram bot..."))

        # Get bot token
        bot_token = os.environ.get(
            "TELEGRAM_BOT_TOKEN", "7898598468:AAG5A2-8d6RYKNmhUOHXfhIs2T7QtJd9AEY"
        )

        # Create bot and dispatcher
        bot = Bot(token=bot_token)
        dp = Dispatcher()

        # Register handlers
        dp.message.register(self.start_command, CommandStart())
        dp.message.register(self.handle_photo, F.photo)
        dp.message.register(self.handle_text, F.text)

        self.stdout.write(self.style.SUCCESS("Bot is running! Press Ctrl+C to stop."))

        # Run bot
        asyncio.run(dp.start_polling(bot))

    async def start_command(self, message: types.Message):
        """Handle /start command."""
        welcome_message = (
            "👋 *Добро пожаловать!*\n\n"
            "Я бот для отметки участников мероприятия *Bond and Data*.\n\n"
            "📸 Отправьте мне *фото QR-кода* с билета участника, "
            "и я отмечу его присутствие.\n\n"
            "Или отправьте *UUID* участника текстом."
        )
        await message.answer(welcome_message, parse_mode=ParseMode.MARKDOWN)

    async def handle_photo(self, message: types.Message, bot: Bot):
        """Handle photo messages - decode QR code and check-in participant."""
        await message.answer("🔍 Сканирую QR-код...")

        try:
            # Get the largest photo
            photo = message.photo[-1]

            # Download photo to bytes
            file = await bot.get_file(photo.file_id)
            photo_bytes = await bot.download_file(file.file_path)

            # Open image and decode QR
            image = Image.open(photo_bytes)
            decoded_objects = decode(image)

            if not decoded_objects:
                await message.answer(
                    "❌ *QR-код не найден*\n\n"
                    "Убедитесь, что QR-код хорошо виден на фото и попробуйте снова.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            # Get UUID from QR code
            uuid_str = decoded_objects[0].data.decode("utf-8")

            # Process check-in
            await self.process_checkin(message, uuid_str)

        except Exception as e:
            await message.answer(
                f"❌ *Ошибка при обработке фото:*\n{str(e)}",
                parse_mode=ParseMode.MARKDOWN,
            )

    async def handle_text(self, message: types.Message):
        """Handle text messages - try to parse as UUID."""
        uuid_str = message.text.strip()
        await self.process_checkin(message, uuid_str)

    async def process_checkin(self, message: types.Message, uuid_str: str):
        """Process participant check-in by UUID."""
        try:
            # Find participant
            participant = await asyncio.to_thread(
                Participant.objects.filter(id=uuid_str).first
            )

            if not participant:
                await message.answer(
                    "❌ *Участник не найден*\n\n"
                    "Проверьте правильность QR-кода или UUID.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            # Check if already checked in
            if participant.is_checked_in:
                await message.answer(
                    f"⚠️ *Участник уже отмечен!*\n\n"
                    f"👤 *{participant.fullname}*\n"
                    f"🏫 {participant.school}, {participant.grade} класс\n"
                    f"📍 {participant.district}\n"
                    f"⏰ Отмечен: {participant.checked_in_at.strftime('%H:%M %d.%m.%Y')}",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            # Check-in participant
            participant.is_checked_in = True
            participant.checked_in_at = timezone.now()
            await asyncio.to_thread(participant.save)

            await message.answer(
                f"✅ *Успешно отмечен!*\n\n"
                f"👤 *{participant.fullname}*\n"
                f"📞 {participant.phone_number}\n"
                f"🏫 {participant.school}, {participant.grade} класс\n"
                f"📍 {participant.district}\n"
                f"👨‍🏫 Учитель: {participant.teacher_fullname}",
                parse_mode=ParseMode.MARKDOWN,
            )

        except Exception as e:
            await message.answer(
                f"❌ *Ошибка:* {str(e)}", parse_mode=ParseMode.MARKDOWN
            )
