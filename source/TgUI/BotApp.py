from typing import Optional, Set

from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from source.Logging import Logger
from source.Database.DBHelper import DataBaseHelper
from source.ChromaAndRAG.ChromaClient import RagClient
from source.TelegramMessageScrapper.Base import Scrapper, ScrapSIG, ChannelRecord
import re, asyncio

# --- Клавиатура --- #
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Задать вопрос")],
        [KeyboardButton(text="ℹ️ Как добавить канал")],
        [KeyboardButton(text="📚 Мои каналы"), KeyboardButton(text="🗑 Удалить канал")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

class BotApp:
    def __init__(self, token: str,db_helper: Optional[DataBaseHelper], rag: RagClient, scrapper: Scrapper):
        self.telegram_ui_logger = Logger("TelegramUI", "network.log")
        self.bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
        self.dispatcher = Dispatcher(storage=MemoryStorage())
        self.router = Router()
        self.dispatcher.include_router(self.router)
        self.__include_handlers()

        self.DataBaseHelper = db_helper
        self.RagClient = rag
        self.Scrapper = scrapper

        self.request_queueue = asyncio.Queue()
        self.response_queue = asyncio.Queue()

        self._request_task: Optional[asyncio.Task] = None
        self._response_task: Optional[asyncio.Task] = None

    def include_db(self, db_helper: DataBaseHelper):
        if self.DataBaseHelper is None:
            self.DataBaseHelper = db_helper

    def __include_handlers(self):
        self.router.message.register(self.__start_handler, F.text == "/start")
        self.router.message.register(self.__ask_question_handler, F.text == "❓ Задать вопрос")
        self.router.message.register(self.__add_command_handler, F.text.in_(["/add", "ℹ️ Как добавить канал"]))
        self.router.message.register(self.__get_channels, F.text.in_(["/get_channels", "📚 Мои каналы"]))
        self.router.message.register(self.__remove_command_handler, F.text.in_(["/remove", "🗑 Удалить канал"]))
        self.router.message.register(self.__forward_message_handler, F.forward_date)
        self.router.message.register(self.__main_text_handler, F.text)
        self.router.callback_query.register(self.__inline_button_handler)

    async def __start_handler(self, message: Message):
        await self.telegram_ui_logger.info(f"User {message.from_user.id} started the bot.")
        await self.bot.set_my_commands([
            BotCommand(command="/start", description="🚀 Перезапустить бота"),
            BotCommand(command="/add", description="ℹ️ Как добавить канал"),
            BotCommand(command="/get_channels", description="📚 Показать мои каналы"),
            BotCommand(command="/remove", description="🗑 Удалить канал"),
        ])
        await message.answer(
            f"👋 Добро пожаловать, {message.from_user.first_name}!\n\nЯ — ваш личный ассистент для работы с информацией из Telegram-каналов.",
            reply_markup=main_keyboard
        )

    @staticmethod
    async def __ask_question_handler(message: Message):
        await message.answer("Просто напишите ваш вопрос в этот чат, и я постараюсь найти на него ответ.", reply_markup=main_keyboard)

    @staticmethod
    async def __add_command_handler(message: Message):
        await message.answer(
            "<b>Чтобы добавить новый канал, есть два простых способа:</b>\n\n" \
            "1. Просто **перешлите** мне любое сообщение из нужного вам публичного канала.\n" \
            "2. Отправьте мне ссылку на канал в формате `@username` или `https://t.me/username`.",
            reply_markup=main_keyboard, disable_web_page_preview=True
        )

    async def __process_channel_addition(self, message: Message, channel_id: int, channel_title: str):
        try:
            try: self.DataBaseHelper.get_user(message.from_user.id)
            except ValueError: await self.DataBaseHelper.create_user(message.from_user.id, message.from_user.first_name)

            try:
                await self.DataBaseHelper.create_channel(channel_id, channel_title)
            except ValueError: 
                pass
            
            user_channels = self.DataBaseHelper.get_user_channels(message.from_user.id)
            if channel_id in user_channels:
                await message.answer(f'Канал "{channel_title}" уже был в вашем списке.', reply_markup=main_keyboard)
                return

            self.DataBaseHelper.update_user_channels(user_id=message.from_user.id, add=[channel_id])

            await self.RagClient.create_collection_if_not_exists(channel_id, channel_title)
            await self.Scrapper.update([ChannelRecord(channel_id=channel_id, action=ScrapSIG.SUB)])

            await message.answer(f'✅ Источник "{channel_title}" успешно добавлен!', reply_markup=main_keyboard)
        except Exception as e:
            await self.telegram_ui_logger.error(f"Error adding channel for user {message.from_user.id}: {e}")
            await message.answer("Произошла ошибка при добавлении канала.", reply_markup=main_keyboard)

    async def __get_channels(self, message: Message):
        try: user_channels = self.DataBaseHelper.get_user_channels(message.from_user.id)
        except ValueError: 
            await message.answer("Вы не зарегистрированы. Добавьте канал, переслав сообщение из него.", reply_markup=main_keyboard)
            return

        if not user_channels: 
            await message.answer("У вас пока нет добавленных каналов.", reply_markup=main_keyboard)
            return
        
        channel_details = self.DataBaseHelper.get_channels_by_ids(user_channels)
        channel_names = [f"• {name}" for id, name in channel_details]
        await message.answer("<b>Ваши источники:</b>\n" + "\n".join(channel_names), reply_markup=main_keyboard)

    async def __get_channels_internal(self, user_id: int):
        try: user_channels = self.DataBaseHelper.get_user_channels(user_id)
        except ValueError: return None
        if not user_channels: return None
        
        channel_details = self.DataBaseHelper.get_channels_by_ids(user_channels)
        return [{"id": id, "name": name} for id, name in channel_details]

    async def __remove_command_handler(self, message: Message):
        channels = await self.__get_channels_internal(message.from_user.id)
        if not channels: 
            await message.answer("У вас нет каналов для удаления.", reply_markup=main_keyboard)
            return
        await self.__send_paginated_channels(message, channels, 1)

    async def __send_paginated_channels(self, message: Message, channels, page: int):
        items_per_page = 5
        start, end = (page - 1) * items_per_page, page * items_per_page
        current_page_channels = channels[start:end]

        inline_keyboard = [[InlineKeyboardButton(text=f"❌ {ch['name']}", callback_data=f"rm:{ch['id']}")] for ch in current_page_channels]

        nav_buttons = []
        if page > 1: nav_buttons.append(InlineKeyboardButton(text="<< Назад", callback_data=f"page:{page - 1}"))
        if end < len(channels): nav_buttons.append(InlineKeyboardButton(text="Вперед >>", callback_data=f"page:{page + 1}"))
        
        if nav_buttons: inline_keyboard.append(nav_buttons)
        
        inline_keyboard.append([InlineKeyboardButton(text="✔️ Готово", callback_data="done_removing")])

        markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        text = "Нажмите на канал, чтобы удалить его:"
        try: await message.edit_text(text, reply_markup=markup)
        except: await message.answer(text, reply_markup=markup)

    async def __inline_button_handler(self, cb: CallbackQuery):
        await cb.answer()
        data = cb.data

        if data.startswith("rm:"):
            channel_id_to_remove = int(data.split(":")[1])
            self.DataBaseHelper.update_user_channels(cb.from_user.id, remove=[channel_id_to_remove])
            
            all_users = self.DataBaseHelper.get_all_users()
            is_channel_still_used = any(channel_id_to_remove in self.DataBaseHelper.get_user_channels(user.id) for user in all_users)

            if not is_channel_still_used:
                await self.telegram_ui_logger.info(f"Channel {channel_id_to_remove} is no longer used by any user. Removing completely.")
                await self.RagClient.delete_channel(channel_id_to_remove)
                self.DataBaseHelper.delete_channel(channel_id_to_remove) 
                await self.Scrapper.update([ChannelRecord(channel_id=channel_id_to_remove, action=ScrapSIG.UNSUB)])

            channels = await self.__get_channels_internal(user_id=cb.from_user.id)
            if not channels:
                await cb.message.edit_text("Все каналы удалены.", reply_markup=None)
                return
            await self.__send_paginated_channels(cb.message, channels, 1)

        elif data.startswith("page:"):
            page = int(data.split(":")[1])
            channels = await self.__get_channels_internal(cb.from_user.id)
            if channels: await self.__send_paginated_channels(cb.message, channels, page)
            else: await cb.message.edit_text("Все каналы удалены.", reply_markup=None)

        elif data == "done_removing":
            await cb.message.delete()
            await self.bot.send_message(cb.from_user.id, "Готово!", reply_markup=main_keyboard)

    async def __forward_message_handler(self, message: Message):
        if message.forward_from_chat and message.forward_from_chat.id:
            await self.__process_channel_addition(message, message.forward_from_chat.id, message.forward_from_chat.title)
        else:
            await message.answer("😔 **Не удалось добавить источник.**\n\nЯ работаю только с **публичными** каналами.", reply_markup=main_keyboard)

    async def __main_text_handler(self, message: Message):
        if message.from_user.id == self.bot.id: return

        match = re.search(r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{5,})', message.text)
        if match:
            try:
                chat = await self.bot.get_chat(f"@{match.group(1)}")
                await self.__process_channel_addition(message, chat.id, chat.title)
            except Exception as e:
                await self.telegram_ui_logger.error(f"Failed to get chat for {match.group(1)}: {e}")
                await message.answer(f"Не удалось найти канал '{match.group(1)}'. Убедитесь, что ссылка верна.", reply_markup=main_keyboard)
            return

        await self.__rag_query_handler(message)

    async def __rag_query_handler(self, message: Message):
        try: user_channels = self.DataBaseHelper.get_user_channels(message.from_user.id)
        except ValueError: 
            await message.answer("Вы не зарегистрированы. Добавьте канал, чтобы задавать вопросы.", reply_markup=main_keyboard)
            return
        if not user_channels: 
            await message.answer("У вас нет источников. Добавьте канал, чтобы я мог отвечать на вопросы.", reply_markup=main_keyboard)
            return

        await self.request_queueue.put((message.from_user.id, message.text, user_channels))
        await message.answer("✅ Ваш запрос принят. Ищу ответ...", reply_markup=main_keyboard)

    async def __request_loop(self):
        while True:
            try:
                user_id, request, channel_ids = await self.request_queueue.get()
                await self.telegram_ui_logger.info(f"Processing RAG request for {user_id}: {request}")
                await self.RagClient.query(user_id, request, channel_ids)
            except Exception as e:
                await self.telegram_ui_logger.error(f"Error in request loop: {e}")

    async def __response_loop(self):
        while True:
            try:
                user_id, response = await self.RagClient.rag_response_queue.get()
                await self.telegram_ui_logger.info(f"Got response from RAG for {user_id}")
                await self.bot.send_message(user_id, response, reply_markup=main_keyboard)
            except Exception as e: 
                await self.telegram_ui_logger.error(f"Failed to send message to {user_id}: {e}")

    async def start(self):
        try:
            # <<< ИЗМЕНЕНИЕ ЗДЕСЬ >>>
            all_users = self.DataBaseHelper.get_all_users()
            active_channel_ids: Set[int] = set()
            for user in all_users:
                user_channels = self.DataBaseHelper.get_user_channels(user.id)
                active_channel_ids.update(user_channels)

            if active_channel_ids:
                records = [ChannelRecord(channel_id=ch_id, action=ScrapSIG.SUB) for ch_id in active_channel_ids]
                await self.Scrapper.update(records)
            # <<<
        except Exception as e:
            await self.telegram_ui_logger.error(f"Failed to initialize scrapper with channels from DB: {e}")

        if self._request_task is None or self._request_task.done(): self._request_task = asyncio.create_task(self.__request_loop())
        if self._response_task is None or self._response_task.done(): self._response_task = asyncio.create_task(self.__response_loop())
        await self.dispatcher.start_polling(self.bot)

    async def stop(self):
        if self._request_task: self._request_task.cancel()
        if self._response_task: self._response_task.cancel()
        await self.bot.session.close()