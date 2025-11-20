
import asyncio

from source.Logging import Logger, LoggerComposer
from source.Database.DBHelper import DataBaseHelper
from source.TgUI.BotApp import BotApp
from source.ChromaAndRAG.ChromaClient import RagClient
from source.TelegramMessageScrapper.Base import Scrapper

from source.DynamicConfigurationLoading import get_config

class TeleRagService:
    """
    The Tele rag Service class is responsible for managing the Telegram message scrapper and the RAG client.
    It handles the initialization, updating, and querying of channels and messages.
    """

    def __init__(self):
        settings = get_config()
        self.settings = settings
        self.logger_composer = LoggerComposer(
            loglevel=settings.log_level,
        )
        self.tele_rag_logger = Logger("TeleRag", "network.log")
        self.Scrapper = Scrapper(
            api_id=settings.pyrogram.api_id,
            api_hash=settings.pyrogram.api_hash,
            history_limit=settings.pyrogram.history_limit,
        )
        self.RagClient = RagClient(
            host=settings.rag.host,
            port=settings.rag.port,
            n_result=settings.rag.n_result,
            model=settings.rag.sentence_transformer_model,
            mistral_api_key=settings.rag.mistral_api_key,
            mistral_model=settings.rag.mistral_model,
            scrapper=self.Scrapper,
        )


        self.BotApp = BotApp(
            token=settings.aiogram.api_key,
            rag=self.RagClient,
            db_helper=None,
        )
        self.logger_composer.set_level_if_not_set()
        self.stop_event = asyncio.Event()
        self.register_stop_signal_handler()

    async def start(self):
        self.__create_db(self.settings)
        await self.tele_rag_logger.info("Starting TeleRagService...")
        await self.RagClient.start_rag()
        await self.Scrapper.scrapper_start()
        await self.BotApp.start()

    async def idle(self):
        await self.tele_rag_logger.info("Waiting for stop signal... Press Ctrl+C to stop.")
        await self.stop_event.wait()
        await self.tele_rag_logger.info("Stop signal received. Stopping TeleRagService...")
        await self.Scrapper.scrapper_stop()
        await self.RagClient.stop()
        await self.BotApp.stop()
        self.stop_event.clear()
        await self.tele_rag_logger.info("TeleRagService stopped.")


    def __stop_signal_handler(self):
        self.stop_event.set()

    def register_stop_signal_handler(self):
        """
        Register a signal handler for stopping the service.
        """
        import signal
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, self.__stop_signal_handler, )
        loop.add_signal_handler(signal.SIGINT, self.__stop_signal_handler, )

    def __create_db(self, settings):
        db_url = f"postgresql://{settings.database.user}:{settings.database.password}@{settings.database.host}:{settings.database.port}/{settings.database.db}"
        self.DataBaseHelper = DataBaseHelper(db_url=db_url)
        self.BotApp.include_db(self.DataBaseHelper)
        del self.settings
