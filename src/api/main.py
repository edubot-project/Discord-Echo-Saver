import asyncio
from contextlib import asynccontextmanager
from typing import List

import discord
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from src import settings
from src.logging_config import setup_base_logging, get_logger
from src.services.DiscordEchoSaver_v1.echosaverbot_v2 import DiscordEchoSaverBot

setup_base_logging()
logger = get_logger("api", "DiscordEchoSaver")

_bot: DiscordEchoSaverBot | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True
    intents.messages = True

    # asyncio.Event propio para saber cuándo el bot está listo.
    # wait_until_ready() de discord.py falla si se llama antes de que login()
    # haya inicializado _connection, lo cual ocurre cuando se usa create_task.
    ready_event = asyncio.Event()

    class _APIBot(DiscordEchoSaverBot):
        async def on_ready(self):
            logger.info(f"Bot conectado como {self.user} — esperando solicitudes HTTP")
            ready_event.set()

    _bot = _APIBot(intents=intents, guild_id_list=[], channel_id_list=[])
    bot_task = asyncio.create_task(_bot.start(settings.DISCORD_BOT_TOKEN))

    await ready_event.wait()
    logger.info("API lista y bot conectado")

    yield

    await _bot.close()
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Discord Echo Saver", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GuildRequest(BaseModel):
    guild_id_list: List[int]


class ChannelRequest(BaseModel):
    channel_id_list: List[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_session():
    return sessionmaker(bind=_bot.engine)()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/channels", status_code=202)
async def update_channels(request: GuildRequest):
    """
    Sincroniza canales y threads de los servidores indicados con discord_channels.
    La operación corre en segundo plano; responde 202 de inmediato.
    """
    async def task():
        session = _new_session()
        try:
            await _bot.update_channels(session, guild_id_list=request.guild_id_list)
        except Exception as e:
            logger.error(f"Error en /channels: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {"status": "accepted", "guild_id_list": request.guild_id_list}


@app.post("/users", status_code=202)
async def update_users(request: GuildRequest):
    """
    Sincroniza miembros de los servidores indicados con discord_users.
    La operación corre en segundo plano; responde 202 de inmediato.
    """
    async def task():
        session = _new_session()
        try:
            await _bot.update_users(session, guild_id_list=request.guild_id_list)
        except Exception as e:
            logger.error(f"Error en /users: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {"status": "accepted", "guild_id_list": request.guild_id_list}


@app.post("/messages", status_code=202)
async def update_messages(request: ChannelRequest):
    """
    Para cada channel_id de la lista, extrae recursivamente los mensajes del
    canal/foro/categoría y de todos sus hijos, y los guarda en discord_messages.
    La operación corre en segundo plano; responde 202 de inmediato.
    """
    async def task():
        session = _new_session()
        try:
            for channel_id in request.channel_id_list:
                await _bot.recursively_save_messages_from_a_root(session, channel_id)
        except Exception as e:
            logger.error(f"Error en /messages: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {"status": "accepted", "channel_id_list": request.channel_id_list}


"""
uvicorn src.api.main:app --reload


"""
