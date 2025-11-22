
from sqlalchemy import create_engine, Column, BigInteger, String, Table, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

user_channels = Table('user_channels', Base.metadata,
    Column('user_id', BigInteger, ForeignKey('users.id')),
    Column('channel_id', BigInteger, ForeignKey('channels.id'))
)

class UserModel(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True)
    name = Column(String)
    channels = relationship("ChannelModel", secondary=user_channels, back_populates="users")

class ChannelModel(Base):
    __tablename__ = 'channels'
    id = Column(BigInteger, primary_key=True)
    name = Column(String)
    subscribers = Column(BigInteger, default=0)
    users = relationship("UserModel", secondary=user_channels, back_populates="channels")
