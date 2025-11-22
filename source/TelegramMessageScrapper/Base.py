"""
This is base file where the collector is defined. The collection logic lies in the collector.py file.
"""
import asyncio
import enum
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from dataclasses import dataclass
from source.Logging import Logger
from typing import Any, Dict, List
from pyrogram.errors import PeerIdInvalid, ChannelInvalid, ChatAdminRequired, ChatWriteForbidden, UserAlreadyParticipant


class ScrapSIG(enum.Enum):
    SUB = 0
    UNSUB = 1

@dataclass
class ChannelRecord:
    channel_id: int
    action: ScrapSIG

class Scrapper:
    """
    The logic is that the bot accepts new channel_ids, if channels database was updated (new channel added or deleted)
    """

    class ScrapperException(Exception):
        pass

    def __init__(self, api_id: str, api_hash: str, history_limit: int):
        self.scrapper_logger = Logger("Scrapper", "network.log")
        self.pyro_client = Client(
            name="TELERAG-MessageScrapper",
            api_id=api_id,
            api_hash=api_hash
        )
        self.channels: Dict[int, str] = {}
        self.message_hist_limit = history_limit
        self.message_handler = None
        self.new_message_queue = asyncio.Queue()
        self.getting_messages_event = asyncio.Event()
        self.running = True


    async def update(self, records: List[ChannelRecord]) -> None:
        if not self.running:
            return
        await self._update(records)

    async def _update(self, records: List[ChannelRecord]) -> None:
        if not self.running:
            return

        await self.scrapper_logger.debug(f"Got update request... Updating {len(records)} channels...")
        for record in records:
            try:
                if record.action == ScrapSIG.SUB:
                    if record.channel_id in self.channels:
                        await self.scrapper_logger.info(f"Channel {record.channel_id} already subscribed. Skipping.")
                        continue

                    try:
                        await self.scrapper_logger.info(f"Trying to join chat {record.channel_id}")
                        await self.pyro_client.join_chat(record.channel_id)
                    except UserAlreadyParticipant:
                        await self.scrapper_logger.info(f"Already a participant in chat {record.channel_id}")
                    # <<< ИЗМЕНЕНИЕ ЗДЕСЬ >>>
                    except (PeerIdInvalid, ChannelInvalid, ChatAdminRequired, ChatWriteForbidden) as e:
                        await self.scrapper_logger.warning(f"Could not join or process channel {record.channel_id}: {e}. Skipping.")
                        continue # Пропускаем этот канал и идем дальше
                    # <<<

                    chat = await self.pyro_client.get_chat(record.channel_id)

                    if not chat or chat.type != ChatType.CHANNEL:
                        await self.scrapper_logger.warning(f"Chat ID {record.channel_id} is not a valid channel. Leaving and skipping.")
                        try: await self.pyro_client.leave_chat(record.channel_id)
                        except: pass
                        continue

                    self.channels[record.channel_id] = chat.title
                    await self.fetch(record.channel_id)
                    await self.update_or_create_message_handler()
                    await self.scrapper_logger.info(f"Successfully subscribed to channel {chat.title} ({record.channel_id})")

                elif record.action == ScrapSIG.UNSUB:
                    if record.channel_id not in self.channels:
                        await self.scrapper_logger.info(f"Channel {record.channel_id} not subscribed. Skipping unsubscription.")
                        continue
                    
                    try: await self.pyro_client.leave_chat(record.channel_id)
                    except Exception as e:
                        await self.scrapper_logger.warning(f"Error leaving chat {record.channel_id}: {e}")

                    del self.channels[record.channel_id]
                    await self.update_or_create_message_handler()
                    await self.scrapper_logger.info(f"Successfully unsubscribed from channel {record.channel_id}")

            except Exception as e:
                await self.scrapper_logger.error(f"An unexpected error occurred while updating for channel {record.channel_id}: {e}. Skipping.")


    async def fetch(self, channel_id: int):
        if not self.running or channel_id not in self.channels:
            return
        
        channel_name = self.channels[channel_id]
        fetched_count = 0
        try:
            async for message in self.pyro_client.get_chat_history(channel_id, limit=self.message_hist_limit):
                if message.text:
                    await self.new_message_queue.put((channel_id, channel_name, message.text))
                    fetched_count += 1
        except Exception as e:
            await self.scrapper_logger.warning(f"An error occurred while fetching messages from {channel_name} ({channel_id}): {e}")
        finally:
            if fetched_count > 0:
                await self.scrapper_logger.debug(f"Fetched and queued {fetched_count} historical messages from {channel_name}.")

    async def update_or_create_message_handler(self) -> None:
        if self.message_handler:
            self.pyro_client.remove_handler(*self.message_handler)
            self.message_handler = None

        if not self.channels:
            await self.scrapper_logger.warning("No channels to listen to. Handler not (re)created.")
            return

        @self.pyro_client.on_message(filters.chat(list(self.channels.keys())))
        async def message_handler(client: Client, message: Any) -> None:
            if not message.text or not message.chat: return

            chat_name = self.channels.get(message.chat.id, "Unknown")
            if self.getting_messages_event.is_set():
                await self.new_message_queue.put((message.chat.id, chat_name, message.text))
                await self.scrapper_logger.debug(f"Queued new message from channel {message.chat.id}")
            else:
                await self.scrapper_logger.warning(f"Dropped new message from channel {message.chat.id} because RAG client is not ready.")

        self.message_handler = self.pyro_client.add_handler(message_handler)
        await self.scrapper_logger.info(f"Message handler updated for {len(self.channels)} channels.")

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Этот ивент теперь снова важен, чтобы цикл не блокировался вечно
        await self.getting_messages_event.wait()
        if not self.running and self.new_message_queue.empty():
            raise StopAsyncIteration
        
        channel_id, chat_name, msg = await self.new_message_queue.get()
        
        if msg is None: # Сигнал к остановке
            raise StopAsyncIteration
        return channel_id, chat_name, msg

    async def scrapper_start(self):
        await self.pyro_client.start()
        await self.scrapper_logger.debug("Scrapper started.")
        self.running = True

    async def scrapper_stop(self):
        await self.scrapper_logger.debug("Stopping scrapper...")
        self.running = False
        self.getting_messages_event.set() # Разблокируем __anext__ для выхода
        await self.new_message_queue.put((None, None, None)) 
        if self.pyro_client.is_connected:
            await self.pyro_client.stop()
        await self.scrapper_logger.debug("Scrapper stopped.")
