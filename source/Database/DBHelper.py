
from typing import List, Optional
from sqlalchemy import create_engine, select, delete, update
from sqlalchemy.orm import sessionmaker, Session, joinedload
from source.Logging import Logger
from source.Database.Models import UserModel, ChannelModel, Base

class DataBaseHelper:
    def __init__(self, db_url: str):
        self.db_logger = Logger("PostgreSQL", "network.log")
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _get_session(self) -> Session:
        return self.Session()

    def create_user(self, user_id: int, name: str) -> None:
        with self._get_session() as session:
            if session.get(UserModel, user_id):
                self.db_logger.warning(f"User '{user_id}' already exists")
                raise ValueError("User already exists")
            user = UserModel(id=user_id, name=name)
            session.add(user)
            session.commit()

    def delete_user(self, user_id: int) -> None:
        with self._get_session() as session:
            user = session.get(UserModel, user_id)
            if not user:
                self.db_logger.warning(f"User '{user_id}' not found")
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
                    user.channels.append(channel)
                    channel.subscribers += 1

            if remove:
                for channel_id in remove:
                    channel = session.get(ChannelModel, channel_id)
                    if channel in user.channels:
                        user.channels.remove(channel)
                        channel.subscribers -= 1
            
            session.commit()

    def get_user(self, user_id: int) -> UserModel:
        """Оставляем для совместимости, но старайся не использовать .channels снаружи."""
        with self._get_session() as session:
            user = session.get(UserModel, user_id)
            if not user:
                raise ValueError("User not found")
            # возвращаем привязанный объект — использовать только поля, не ленивые связи
            return user

    def get_user_channels(self, user_id: int) -> list[int]:
        """Вернуть список ID каналов пользователя (без DetachedInstanceError)."""
        with self._get_session() as session:
            user = (
                session.query(UserModel)
                .options(joinedload(UserModel.channels))
                .get(user_id)
            )
            if not user:
                raise ValueError("User not found")

            return [ch.id for ch in user.channels]

    def create_channel(self, channel_id: int, name: str) -> None:
        with self._get_session() as session:
            if session.get(ChannelModel, channel_id):
                self.db_logger.warning(f"Channel '{channel_id}' already exists. Will not create one.")
                raise ValueError("Channel already exists")
            channel = ChannelModel(id=channel_id, name=name)
            session.add(channel)
            session.commit()

    def delete_channel(self, channel_id: int) -> None:
        with self._get_session() as session:
            channel = session.get(ChannelModel, channel_id)
            if not channel:
                raise ValueError("Channel not found")

            if channel.subscribers > 0:
                raise ValueError("Channel has subscribers")

            session.delete(channel)
            session.commit()

    def get_channel(self, channel_id: int) -> ChannelModel:
        with self._get_session() as session:
            channel = session.get(ChannelModel, channel_id)
            if not channel:
                raise ValueError("Channel not found")
            return channel
