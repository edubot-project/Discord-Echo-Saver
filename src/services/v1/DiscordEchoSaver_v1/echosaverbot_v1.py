import discord
from typing import List
from src import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from src import models
from typing import Union
import time



class DiscordEchoSaverBot(discord.Client):
    def __init__(self, *, intents : discord.Intents, guild_id_list : List, guild_id : int, root_id : int):  
        super().__init__(intents=intents)
        self.engine = create_engine(settings.APP_CONN_STRING)
        self.guild_id_list = guild_id_list
        self.guild_id = guild_id
        self.root_id = root_id

 
    async def on_ready(self):
        print(f"🤖 Conectado como {self.user}")
        Session = sessionmaker(bind=self.engine)
        session = Session()

        #await self.save_guild_data(session)
        #await self.save_channel_data_from_server(session=session, guild_id_list=self.guild_id_list)
        #await self.recursively_save_messages_from_a_root(session=session, root_id=self.root_id)
        await self.save_user_data(session=session, guild_id_list=self.guild_id_list)

        session.close()

        await self.close()




    async def save_guild_data(self, session : Session):
        print("\n📦 Guardando información de servidores:")
        for guild in self.guilds:
            existing_guild = (
                session.query(models.DiscordGuild).filter_by(id=guild.id).first()
            )
            if not existing_guild:
                discord_guild_record = models.DiscordGuild(
                    id=guild.id, name=guild.name, create_at=guild.created_at
                )
                session.add(discord_guild_record)
                print(f"✅ Guild '{guild.name}' ({guild.id}) guardado.")
            else:
                print(f"⏩ Guild '{guild.name}' ({guild.id}) ya existe. Saltando.")
        session.commit()




    async def save_user_data(self, session: Session, guild_id_list: List):
        for guild_id in guild_id_list:
            guild = await self.fetch_guild(guild_id)
            print(f"  📝 Procesando {guild.name} ({guild.id})")

            # 1. Traer todos los IDs que ya tenemos en este guild para comparar en memoria
            existing_user_ids = {
                res[0] for res in session.query(models.DiscordUser.id)
                .filter_by(guild_id=guild.id).all()
            }

            new_users = 0
            async for member in guild.fetch_members(limit=None):
                if member.id not in existing_user_ids:
                    discord_user_record = models.DiscordUser(
                        id=member.id,
                        guild_id=guild.id,
                        is_bot=member.bot,
                        global_name=member.name,         # ej: 'juan_perez'
                        display_name=member.display_name, # ej: 'Juan | Admin'
                        joined_at=member.joined_at
                    )
                    session.add(discord_user_record)
                    new_users += 1
                    
                    # Opcional: commit por lotes cada 100 para no saturar
                    if new_users % 100 == 0:
                        session.commit()

            session.commit()
            print(f"    ✅ Se agregaron {new_users} usuarios nuevos.")

    


    async def save_channel_data_from_server(self, session: Session, guild_id_list):
        print("\n📺 Guardando información de canales en guild_id_list:")
        guild_id_set = set(guild_id_list)

        for guild in self.guilds:
            if guild.id not in guild_id_set:
                continue

            print(f"  📝 Procesando canales del servidor: {guild.name} ({guild.id})")

            
            # FORZAR A LA API A TRAER TODOS LOS HILOS ACTIVOS DEL SERVIDOR (Salva problemas de Caché)
            try:
                active_threads = await guild.active_threads()
                for thread in active_threads:
                    await self._save_thread(session, guild, thread, parent_id=thread.parent_id)
            except Exception as e:
                print(f"  ⚠️ Error obteniendo hilos activos de la guild: {e}")
            

            for channel in guild.channels:

                # -------------------------
                # 1. Determinar tipo
                # -------------------------
                
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
                    continue  # ignorar otros tipos

                # -------------------------
                # 2. Guardar canal base
                # -------------------------
                existing_channel = (
                    session.query(models.DiscordChannel)
                    .filter_by(id=channel.id, guild_id=guild.id)
                    .first()
                )

                if not existing_channel:
                    record = models.DiscordChannel(
                        id=channel.id,
                        guild_id=guild.id,
                        name=channel.name,
                        parent_channel_id=parent_id,
                        channel_type=channel_type,
                        create_at=channel.created_at,
                        last_messages_at=None,
                    )
                    session.add(record)
                    print(f"    ✅ Canal '{channel.name}' ({channel_type}) guardado.")
                else:
                    print(f"    ⏩ Canal '{channel.name}' ya existe.")

                # -------------------------
                # 3. Procesar THREADS
                # -------------------------
                if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):

                    # 🔹 Threads activos
                    for thread in channel.threads:
                        await self._save_thread(session, guild, thread, parent_id=channel.id)

                    # 🔹 Threads archivados
                    try:
                        async for thread in channel.archived_threads(limit=None):
                            await self._save_thread(session, guild, thread, parent_id=channel.id)
                    except Exception as e:
                        print(f"    ⚠️ Error obteniendo threads archivados en {channel.name}: {e}")
                    
                    # 🔹 Threads archivados PRIVADOS (AQUÍ ESTÁ LA MAGIA)
                    # Necesitamos validar que el bot tenga permisos para leerlos o fallará
                    # 🔹 Threads archivados PRIVADOS
                    permissions = channel.permissions_for(guild.me)

                    # IMPORTANTE: Para ver hilos privados archivados se requiere 'manage_threads' 
                    # o haber sido parte de ellos.
                    if permissions.manage_threads or permissions.administrator:
                        try:
                            async for thread in channel.archived_threads(limit=None, private=True):
                                await self._save_thread(session, guild, thread, parent_id=channel.id)
                                print(f"      🕵️ Hilo privado encontrado: {thread.name}")
                        except discord.Forbidden:
                            print(f"    ⛔ Acceso denegado a hilos privados en {channel.name} (Falta Manage Threads).")
                        except Exception as e:
                            print(f"    ⚠️ Error en hilos privados de {channel.name}: {e}")
                    else:
                        print(f"    ℹ️ Saltando hilos privados en {channel.name} (Sin permiso Manage Threads).")

            session.commit()






    async def _save_thread(self, session : Session, guild : discord.guild.Guild, thread : discord.threads.Thread, parent_id : int):
        existing_thread = (
            session.query(models.DiscordChannel)
            .filter_by(id=thread.id, guild_id=guild.id)
            .first()
        )

        if not existing_thread:
            record = models.DiscordChannel(
                id=thread.id,
                guild_id=guild.id,
                name=thread.name,
                parent_channel_id=parent_id,
                channel_type="thread",
                create_at=thread.created_at,
                last_messages_at=None,
            )
            session.add(record)
            print(f"      🧵 Thread '{thread.name}' guardado.")
        else:
            print(f"      ⏩ Thread '{thread.name}' ya existe.")






    async def _get_and_save_messages_from_channel(
        self, session: Session, channel: discord.TextChannel
    ):
        count = 0
        latest_message_timestamp = None

        try:
            # 🔹 1. Obtener el canal en BD
            db_channel = (
                session.query(models.DiscordChannel)
                .filter_by(id=channel.id, guild_id=channel.guild.id)
                .first()
            )

            after = None

            # 🔹 2. Si ya se ha ejecutado antes
            if db_channel and db_channel.last_messages_at is not None:
                print(f"🔄 Canal '{channel.name}' ya procesado antes. Buscando último mensaje...")

                last_msg = (
                    session.query(models.DiscordMessage)
                    .filter_by(channel_id=channel.id)
                    .order_by(models.DiscordMessage.message_create_at.desc())
                    .first()
                )

                if last_msg:
                    after = last_msg.message_create_at
                    print(f"⏩ Continuando desde: {after}")
                else:
                    print("⚠️ last_messages_at existe pero no hay mensajes en BD.")

            else:
                print(f"🆕 Primera vez procesando canal '{channel.name}'")

            # 🔹 3. Extraer mensajes desde 'after'
            async for msg in channel.history(
                limit=None,
                oldest_first=True,
                after=after
            ):
                exists = (
                    session.query(models.DiscordMessage.id)
                    .filter_by(id=msg.id)
                    .first()
                )
                if exists:
                    continue

                attachments = [
                    {"filename": a.filename, "url": a.url, "size": a.size}
                    for a in msg.attachments
                ]

                discord_message_record = models.DiscordMessage(
                    id=msg.id,
                    guild_id=channel.guild.id,
                    channel_id=channel.id,
                    user_id=msg.author.id,
                    user_name=msg.author.name,
                    user_display_name=msg.author.display_name,
                    content=msg.content if msg.content else None,
                    reply_to=(
                        msg.reference.message_id if msg.reference else None
                    ),
                    attachments=attachments if attachments else None,
                    attachments_explanation=None,
                    message_create_at=msg.created_at,
                )

                session.add(discord_message_record)
                count += 1
                latest_message_timestamp = msg.created_at

                if count % 500 == 0:
                    session.commit()
                    print(f"{count} mensajes guardados en '{channel.name}'...")

            session.commit()

            print(f"✅ {count} mensajes nuevos en '{channel.name}'.")

            # 🔹 4. Actualizar timestamp SOLO si hubo nuevos mensajes
            if latest_message_timestamp:
                db_channel.last_messages_at = latest_message_timestamp
                session.add(db_channel)
                session.commit()

                print(
                    f"🕒 last_messages_at actualizado a {latest_message_timestamp}"
                )

        except discord.Forbidden:
            print(
                f"⚠️ Sin permisos en '{channel.name}' ({channel.id})."
            )
            session.rollback()

        except Exception as e:
            print(
                f"❌ Error en canal '{channel.name}' ({channel.id}): {e}"
            )
            session.rollback()








    async def recursively_save_messages_from_a_root(self, session: Session, root_id: int):
            print(f"--- 🔍 Procesando nodo con id: {root_id} ---")
            
            # 1. Obtener registro de la BD
            channel_record = session.query(models.DiscordChannel).filter_by(id=root_id).first()
            if not channel_record:
                print(f"⚠️ El canal con ID {root_id} no existe en la base de datos.")
                return

            # 2. Intentar obtener el objeto de canal de Discord (Cache -> API)
            root = self.get_channel(root_id)
            if root is None:
                try:
                    print(f"🌐 Buscando en la API de Discord (no estaba en caché)...")
                    root = await self.fetch_channel(root_id)
                except discord.NotFound:
                    print(f"❌ Error: El canal/hilo {root_id} no se encontró en Discord.")
                    return
                except discord.Forbidden:
                    print(f"⛔ Error: Sin permisos para acceder al canal/hilo {root_id}.")
                    return
                except Exception as e:
                    print(f"❌ Error inesperado al obtener canal {root_id}: {e}")
                    return

            # 3. Lógica según el tipo de canal
            print(f"📂 Tipo detectado: {channel_record.channel_type}")

            # Si es texto o hilo, extraemos sus mensajes
            if channel_record.channel_type in ["text", "thread"]:
                print(f"📥 Extrayendo mensajes de: {root.name}")
                await self._get_and_save_messages_from_channel(session=session, channel=root)

            # 4. Procesar hijos (Recursividad)
            # Esto aplica para categorías, foros y canales de texto (que pueden tener hilos)
            son_channels_record = session.query(models.DiscordChannel).filter_by(parent_channel_id=root_id).all()
            
            if son_channels_record:
                print(f"🌿 Procesando {len(son_channels_record)} hijos de '{channel_record.name}'")
                for son in son_channels_record:
                    await self.recursively_save_messages_from_a_root(session=session, root_id=son.id)
            else:
                print(f"🍃 El nodo '{channel_record.name}' no tiene hijos.")            
            
        



        
    







if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True  # Necesario para fetch_members TODO: aparentemente el token no tiene los permisos necesarios, esto genera un error
    intents.messages = True

    GUILD_ID_LIST = [772855809406271508, 1308885706621452369]

    # GUILD_ID = 772855809406271508 # UNERGY

    # GUILD_ID = 1308885706621452369 # The Sun Factory

    GUILD_ID = 772855809406271508


    bot = DiscordEchoSaverBot(intents=intents, guild_id_list=GUILD_ID_LIST, guild_id=GUILD_ID, root_id=1311706520467144808)
    bot.run(settings.DISCORD_BOT_TOKEN)
    #bot.run(settings.DULCINEA_DISCORD_BOT_TOKEN)


"""
python3 -m src.services.DiscordEchoSaverv1.botv3



"""