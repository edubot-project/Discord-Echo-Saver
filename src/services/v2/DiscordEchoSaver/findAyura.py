import discord
from typing import List
from src import settings
from src.logging_config import setup_base_logging, get_logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src import discord_models as models


setup_base_logging()
logger = get_logger("echosaverbot_v2", "DiscordEchoSaver")


class DiscordEchoSaverBot(discord.Client):
    def __init__(
        self,
        *,
        intents: discord.Intents,
        guild_id_list: List[int],
        channel_id_list: List[int],
    ):
        super().__init__(intents=intents)
        self.engine = create_engine(settings.APP_CONN_STRING)
        self.guild_id_list = guild_id_list
        self.channel_id_list = channel_id_list

    async def on_ready(self):
        logger.info(f"Conectado como {self.user}")
        SessionLocal = sessionmaker(bind=self.engine)
        session = SessionLocal()
        try:
            await self.update_channels(session)
            # await self.update_users(session)
            # for channel_id in self.channel_id_list:
            #     await self.recursively_save_messages_from_a_root(session, channel_id)
        finally:
            session.close()
        await self.close()

    # -------------------------------------------------------------------------
    # CHANNELS
    # -------------------------------------------------------------------------

    async def update_channels(self, session: Session, guild_id_list: List[int] | None = None):
        """
        Para cada guild en guild_id_list, sincroniza todos los canales y
        threads (activos, archivados y privados) con la tabla discord_channels.
        Si el canal ya existe, actualiza su nombre. Si no existe, lo inserta.
        guild_id_list sobreescribe self.guild_id_list si se proporciona.
        """
        logger.info("Iniciando actualización de canales...")
        guild_id_list = guild_id_list if guild_id_list is not None else self.guild_id_list

        for guild_id in guild_id_list:
            guild = self.get_guild(guild_id)
            if guild is None:
                logger.warning(f"Guild {guild_id} no encontrado en caché, intentando fetch...")
                try:
                    guild = await self.fetch_guild(guild_id)
                except Exception as e:
                    logger.error(f"No se pudo obtener el guild {guild_id}: {e}")
                    continue

            logger.info(f"Procesando canales de: {guild.name} ({guild.id})")

            # Threads activos del guild (evita problemas de caché)
            try:
                active_threads = await guild.active_threads()
                for thread in active_threads:
                    self._upsert_channel_record(session, guild, thread, channel_type="thread", parent_id=thread.parent_id)
            except Exception as e:
                logger.error(f"Error obteniendo hilos activos de {guild.name}: {e}")

            for channel in guild.channels:
                if isinstance(channel, discord.CategoryChannel):
                    channel_type = "category"
                    parent_id = None
                elif isinstance(channel, discord.TextChannel):
                    channel_type = "text"
                    parent_id = channel.category_id
                elif isinstance(channel, discord.ForumChannel):
                    channel_type = "forum"
                    parent_id = channel.category_id
                else:
                    continue

                self._upsert_channel_record(session, guild, channel, channel_type=channel_type, parent_id=parent_id)

                if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                    for thread in channel.threads:
                        self._upsert_channel_record(session, guild, thread, channel_type="thread", parent_id=channel.id)

                    try:
                        async for thread in channel.archived_threads(limit=None):
                            self._upsert_channel_record(session, guild, thread, channel_type="thread", parent_id=channel.id)
                    except Exception as e:
                        logger.error(f"Error obteniendo threads archivados en {channel.name}: {e}")

                    permissions = channel.permissions_for(guild.me)
                    if permissions.manage_threads or permissions.administrator:
                        try:
                            async for thread in channel.archived_threads(limit=None, private=True):
                                self._upsert_channel_record(session, guild, thread, channel_type="thread", parent_id=channel.id)
                        except discord.Forbidden:
                            logger.warning(f"Acceso denegado a hilos privados en {channel.name}.")
                        except Exception as e:
                            logger.error(f"Error en hilos privados de {channel.name}: {e}")
                    else:
                        logger.debug(f"Sin permiso para hilos privados en {channel.name}, saltando.")

            session.commit()
            logger.info(f"Canales de {guild.name} actualizados.")

    def _upsert_channel_record(
        self,
        session: Session,
        guild: discord.Guild,
        channel,
        channel_type: str,
        parent_id: int | None,
    ):
        existing = session.query(models.DiscordChannel).filter_by(id=channel.id).first()
        if existing:
            if existing.name != channel.name:
                logger.info(f"Canal renombrado: '{existing.name}' -> '{channel.name}' ({channel.id})")
                existing.name = channel.name
        else:
            record = models.DiscordChannel(
                id=channel.id,
                guild_id=guild.id,
                name=channel.name,
                channel_type=channel_type,
                parent_channel_id=parent_id,
                create_at=channel.created_at,
                last_messages_at=None,
            )
            session.add(record)
            logger.info(f"Canal nuevo insertado: '{channel.name}' ({channel_type}, {channel.id})")

    # -------------------------------------------------------------------------
    # USERS
    # -------------------------------------------------------------------------

    async def update_users(self, session: Session, guild_id_list: List[int] | None = None):
        """
        Para cada guild en guild_id_list, sincroniza todos los miembros con
        la tabla discord_users.
        Inserta usuarios nuevos y actualiza global_name/display_name si cambiaron.
        guild_id_list sobreescribe self.guild_id_list si se proporciona.
        """
        logger.info("Iniciando actualización de usuarios...")
        guild_id_list = guild_id_list if guild_id_list is not None else self.guild_id_list

        for guild_id in guild_id_list:
            try:
                guild = await self.fetch_guild(guild_id)
            except Exception as e:
                logger.error(f"No se pudo obtener el guild {guild_id}: {e}")
                continue

            logger.info(f"Procesando usuarios de: {guild.name} ({guild.id})")

            existing_users: dict[int, models.DiscordUser] = {
                user.id: user
                for user in session.query(models.DiscordUser).filter_by(guild_id=guild.id).all()
            }

            new_count = 0
            updated_count = 0

            async for member in guild.fetch_members(limit=None):
                if member.id in existing_users:
                    db_user = existing_users[member.id]
                    changed = False
                    if db_user.global_name != member.name:
                        db_user.global_name = member.name
                        changed = True
                    if db_user.display_name != member.display_name:
                        db_user.display_name = member.display_name
                        changed = True
                    if changed:
                        updated_count += 1
                else:
                    record = models.DiscordUser(
                        id=member.id,
                        guild_id=guild.id,
                        is_bot=member.bot,
                        global_name=member.name,
                        display_name=member.display_name,
                        joined_at=member.joined_at,
                    )
                    session.add(record)
                    new_count += 1

                if (new_count + updated_count) % 100 == 0 and (new_count + updated_count) > 0:
                    session.commit()

            session.commit()
            logger.info(f"{guild.name}: {new_count} usuarios nuevos, {updated_count} actualizados.")




if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True
    intents.messages = True

    GUILD_ID_LIST = [772855809406271508, 1308885706621452369]
    CHANNEL_ID_LIST = [1311706520467144808]

    bot = DiscordEchoSaverBot(
        intents=intents,
        guild_id_list=GUILD_ID_LIST,
        channel_id_list=CHANNEL_ID_LIST,
    )
    bot.run(settings.DISCORD_BOT_TOKEN)
    # bot.run(settings.DULCINEA_DISCORD_BOT_TOKEN)


"""
python3 -m src.services.v2.DiscordEchoSaver.findAyura


"""
