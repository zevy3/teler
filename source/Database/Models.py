
from sqlalchemy import create_engine, Column, Integer, String, Table, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

user_channels = Table('user_channels', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('channel_id', Integer, ForeignKey('channels.id'))
)

class UserModel(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    channels = relationship("ChannelModel", secondary=user_channels, back_populates="users")

class ChannelModel(Base):
    __tablename__ = 'channels'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    subscribers = Column(Integer, default=0)
    users = relationship("UserModel", secondary=user_channels, back_populates="channels")
