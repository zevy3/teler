
from typing import List, Optional, Tuple
from sqlalchemy import create_engine, select, delete, update
from sqlalchemy.orm import sessionmaker, Session, joinedload
from source.Logging import Logger
from source.Database.Models import UserModel, ChannelModel, Base, user_channels

class DataBaseHelper:
    def __init__(self, db_url: str):
        self.db_logger = Logger("PostgreSQL", "network.log")
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _get_session(self) -> Session:
        return self.Session()

    async def create_user(self, user_id: int, name: str) -> None:
        with self._get_session() as session:
            if session.get(UserModel, user_id):
                await self.db_logger.warning(f"User '{user_id}' already exists")
                raise ValueError("User already exists")
            user = UserModel(id=user_id, name=name)
            session.add(user)
            session.commit()

    def get_all_users(self) -> List[UserModel]:
        """Возвращает список всех пользователей."""
        with self._get_session() as session:
            return session.query(UserModel).all()

    async def delete_user(self, user_id: int) -> None:
        with self._get_session() as session:
            user = session.get(UserModel, user_id)
            if not user:
                await self.db_logger.warning(f"User '{user_id}' not found")
                raise ValueError("User not found")
            session.delete(user)
            session.commit()

    def update_user_channels(self, user_id: int, add: Optional[List[int]] = None, remove: Optional[List[int]] = None) -> None:
        with self._get_session() as session:
            user = session.get(UserModel, user_id)
            if not user:
                raise ValueError("User not found")

            if add:
                for channel_id in add:
                    channel = session.get(ChannelModel, channel_id)
                    if not channel:
                        raise ValueError(f"Channel {channel_id} does not exist")
                    if channel not in user.channels:
                        user.channels.append(channel)

            if remove:
                for channel_id in remove:
                    delete_stmt = delete(user_channels).where(
                        user_channels.c.user_id == user_id,
                        user_channels.c.channel_id == channel_id
                    )
                    session.execute(delete_stmt)
            
            session.commit()

    def get_user(self, user_id: int) -> UserModel:
        with self._get_session() as session:
            user = session.get(UserModel, user_id)
            if not user:
                raise ValueError("User not found")
            return user

    def get_user_channels(self, user_id: int) -> list[int]:
        with self._get_session() as session:
            user = (
                session.query(UserModel)
                .options(joinedload(UserModel.channels))
                .filter(UserModel.id == user_id)
                .one_or_none()
            )
            if not user:
                return []
            return [ch.id for ch in user.channels]

    async def create_channel(self, channel_id: int, name: str) -> None:
        with self._get_session() as session:
            if session.get(ChannelModel, channel_id):
                await self.db_logger.warning(f"Channel '{channel_id}' already exists. Will not create one.")
                return
            channel = ChannelModel(id=channel_id, name=name)
            session.add(channel)
            session.commit()

    def delete_channel(self, channel_id: int) -> None:
        with self._get_session() as session:
            channel = session.get(ChannelModel, channel_id)
            if not channel:
                return
            session.delete(channel)
            session.commit()

    def get_channel(self, channel_id: int) -> ChannelModel:
        with self._get_session() as session:
            channel = session.get(ChannelModel, channel_id)
            if not channel:
                raise ValueError("Channel not found")
            return channel

    def get_channels_by_ids(self, channel_ids: List[int]) -> List[Tuple[int, str]]:
        """Возвращает список кортежей (id, name) для заданных ID каналов."""
        if not channel_ids:
            return []
        with self._get_session() as session:
            channels = session.query(ChannelModel).filter(ChannelModel.id.in_(channel_ids)).all()
            return [(ch.id, ch.name) for ch in channels]

    def get_all_channels(self) -> List[Tuple[int, str]]:
        """Возвращает список всех каналов в виде кортежей (id, name)."""
        with self._get_session() as session:
            channels = session.query(ChannelModel).all()
            return [(ch.id, ch.name) for ch in channels]