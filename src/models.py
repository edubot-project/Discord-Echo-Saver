from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    DateTime,
    Text,
    func,
    JSON,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint
)
from pgvector.sqlalchemy import Vector



class Base(DeclarativeBase):
    pass



class DiscordGuild(Base):
    __tablename__ = "discord_servers"

    id = Column(BigInteger, primary_key=True)
    name = Column(String)
    create_at = Column(DateTime, index=True)  # fecha de creacion del server
    inserted_at = Column(DateTime, server_default=func.now())



class DiscordUser(Base):
    __tablename__ = "discord_users"

    id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("discord_servers.id"), primary_key=True)
    is_bot = Column(Boolean, default=False, index=True)
    global_name = Column(String)  # El username real/único de Discord
    display_name = Column(String) # El apodo en ese servidor específico
    joined_at = Column(DateTime, index=True)
    inserted_at = Column(DateTime, server_default=func.now())



class DiscordChannel(Base):
    __tablename__ = "discord_channels"

    id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("discord_servers.id"))
    name = Column(String)
    channel_type = Column(String)
    parent_channel_id = Column(BigInteger)  # Si es un hilo, cual es el canal del hilo
    create_at = Column(DateTime, index=True)
    last_messages_at = Column(DateTime, index=True)  # Fecha del ultimo mensaje
    inserted_at = Column(DateTime, server_default=func.now())



# author.display_name
class DiscordMessage(Base):
    __tablename__ = "discord_messages"

    id = Column(BigInteger, unique=True, index=True, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("discord_servers.id"), index=True)
    channel_id = Column(BigInteger, ForeignKey("discord_channels.id"), index=True)
    # user_id y user_name no son claves foraneas dado que pueden haver DiscordUser que no estan en DiscordMessage
    user_id = Column(BigInteger, index=True)  # Autor del mensaje
    user_name = Column(String)
    user_display_name = Column(String)

    content = Column(Text, nullable=True)
    reply_to = Column(BigInteger, nullable=True)
    attachments = Column(JSON)
    attachments_explanation = Column(Text, nullable=True) # explicacion de attachments en lenguaje natural, ej si es una imagen, descripcion de esta
    message_create_at = Column(DateTime, index=True)
    inserted_at = Column(DateTime, server_default=func.now())



# CREATE EXTENSION IF NOT EXISTS vector;

#ALTER TABLE channel_chronological_summary 
#ADD COLUMN last_message_id BIGINT REFERENCES discord_messages(id);

class DiscordChannelChronologicalSummary(Base):
    __tablename__="channel_chronological_summary"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("discord_channels.id"))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    number_messages = Column(Integer)
    #last_message_id = Column(BigInteger, ForeignKey("discord_messages.id"))
    summary = Column(Text, nullable=True)
    summary_embedding = Column(Vector[3072])
    #rag_summary = Column(Text)
    key_words = Column(JSON, nullable=True)





