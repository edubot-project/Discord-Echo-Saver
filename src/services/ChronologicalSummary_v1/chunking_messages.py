from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.engine import Engine
import pandas as pd
from src import models
from datetime import datetime
from typing import List

# TODO: AL PARECER HAY UN ERROR EN LA CHUNKENIZACION DE LOS CANALES CON ID 1366127509774532638, 1370774052112826419, 1313134634904846396, 1313504722459820122 !!!!!!


def merge_summary_chunks(session: Session, ids: List[int]):
    # Obtener los registros a fusionar
    db_records = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.id.in_(ids)  # Nota: usa .in_() en lugar de "in"
    ).order_by(models.DiscordChannelChronologicalSummary.start_time).all()
    
    if not db_records:
        return None
    
    start = db_records[0].start_time
    end = db_records[-1].end_time
    
    # Opcional: Aquí puedes combinar otros campos como 'content' si es necesario
    # Por ejemplo: combined_content = " ".join([record.content for record in db_records])
    
    # Eliminar los registros existentes
    for record in db_records:
        session.delete(record)
    
    # Crear el nuevo registro
    new_record = models.DiscordChannelChronologicalSummary(
        start_time=start,
        end_time=end,
        # Asegúrate de incluir otros campos obligatorios aquí
        # Por ejemplo: channel_id=db_records[0].channel_id,
        # content=combined_content, etc.
    )
    
    session.add(new_record)
    # session.flush()  # Opcional: para obtener el ID del nuevo registro
    
    # El commit se debe hacer fuera de la función o puedes agregar:
    # session.commit()
    
    return new_record




def chunking_messages_by_channel(engine: Engine, session: Session, channel_id: int, min_msg: int = 50):

    channel = session.query(models.DiscordChannel).filter_by(id=channel_id).first()
    if channel.channel_type in {"forum", "category"}:
        print(f"El canal {channel.name} es un foro o una categoría. Se ignorara este canal para la chunkenizacion")
        return 
    


    record = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.channel_id == channel_id
    ).order_by(models.DiscordChannelChronologicalSummary.start_time.desc()).first()

    
    if record is None:
        print(f"No se ha guardado ningun registro en DiscordChannelChronologicalSummary del canal {channel_id}")
        print("Se porcederá con la chunkenizacion del canal")
        last_saved_message = None
    else:
        print(f"Se ha encontrado registros del canal {channel_id}. Se intentará chunkenizar nuevos mensajes de este mismo canal")
        last_saved_message = record.start_time
        pass

    query = text("""
        SELECT
            COUNT(dm.id) as total_messages,
            DATE_TRUNC('week', dm.message_create_at) as week_start_by,
            DATE_TRUNC('week', dm.message_create_at) + INTERVAL '7 days' - INTERVAL '1 second' as week_end_by
        FROM discord_messages dm
        WHERE 
            dm.channel_id = :channel_id AND
            (
                :last_saved_message IS NULL OR
                dm.message_create_at > :last_saved_message
            )
        GROUP BY week_start_by
        ORDER BY week_start_by
    """)
    df = pd.read_sql(query, engine, params={"channel_id": channel_id, "last_saved_message":last_saved_message})

    if df.empty:
        print(f"df es vacio, por lo tanto no hay mensajes a chunkenizar del canal {channel_id}")
        return

    summary_list = []
    x = 0
    # Inicializamos con los datos de la primera fila
    current_count = df.loc[0, "total_messages"]
    
    # Un solo puntero 'y' para recorrer las semanas
    for y in range(len(df)):
        # Si ya alcanzamos el mínimo y no es la última fila, cerramos este chunk
        # (Excepto si es el último, que se maneja fuera del loop o al final)
        if current_count >= min_msg and y < len(df) - 1:
            summary_list.append({
                'summary_from': df.loc[x, "week_start_by"],
                'summary_end': df.loc[y, "week_end_by"],
                'messages_count': current_count
            })
            x = y + 1
            if x < len(df):
                current_count = df.loc[x, "total_messages"]
        else:
            # Si no hemos llegado al mínimo, sumamos la siguiente semana (si existe)
            if y + 1 < len(df):
                current_count += df.loc[y + 1, "total_messages"]

    # Agregar el último remanente
    if x < len(df):
        summary_list.append({
            'summary_from': df.loc[x, "week_start_by"],
            'summary_end': df.loc[len(df)-1, "week_end_by"],
            'messages_count': current_count
        })

    # Lógica de fusión: Si el último chunk es muy pequeño, unirlo al penúltimo
    if len(summary_list) > 1 and summary_list[-1]['messages_count'] < min_msg:
        last = summary_list.pop()
        summary_list[-1]['summary_end'] = last['summary_end']
        summary_list[-1]['messages_count'] += last['messages_count']

    
    first_dict = summary_list[0]
    first_message_in_df = session.query(models.DiscordMessage).filter(
        models.DiscordMessage.channel_id == channel_id,
        models.DiscordMessage.message_create_at >= first_dict['summary_from'],
        models.DiscordMessage.message_create_at <= first_dict['summary_end']
    ).order_by(models.DiscordMessage.channel_id).first()


    last_dict = summary_list[-1]
    last_message_in_df = session.query(models.DiscordMessage).filter(
        models.DiscordMessage.channel_id == channel_id,
        models.DiscordMessage.message_create_at >= last_dict['summary_from'],
        models.DiscordMessage.message_create_at <= last_dict['summary_end']
    ).order_by(models.DiscordMessage.message_create_at.desc()).first()

    summary_list[0]['summary_from'] = first_message_in_df.message_create_at
    summary_list[-1]['summary_end'] = last_message_in_df.message_create_at



    # Guardado en base de datos
    for dicc in summary_list:
        discord_summary_record = models.DiscordChannelChronologicalSummary(
            channel_id=channel_id,
            start_time=dicc["summary_from"],
            number_messages=int(dicc["messages_count"]),
            end_time=dicc["summary_end"],
            summary=None,
            key_words=None
        )
        session.add(discord_summary_record)
    
    # Hacer commit una sola vez por canal para mejorar rendimiento
    session.commit()
    print(f"Canal {channel_id}: {len(summary_list)} particiones guardadas.")

    



def chunking_recursively_by_channel_id(engine: Engine, session: Session, channel_id: int, min_msg: int = 50):
    print(f"chunkenizadodo recursivamente el canal {channel_id}")
    chunking_messages_by_channel(engine=engine, session=session, channel_id=channel_id, min_msg=min_msg)

    channels_records = session.query(models.DiscordChannel).filter_by(parent_channel_id=channel_id).all()
    print(f"hay {len(channels_records)} en channels_records")
    if channels_records is None:
        print(f"El canal con id {channel_id} no tiene hijos")
        return
    
    for obj in channels_records:
        chunking_recursively_by_channel_id(engine=engine, session=session, channel_id=obj.id, min_msg=min_msg)
        print("\n\n")
    


if __name__=="__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src import settings
    from src import models
    
    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()


    # chunking_messages_by_channel(engine=engine, session=session, channel_id=1478852628019675237)

    chunking_recursively_by_channel_id(engine=engine, session=session, channel_id=1309953285582491649)



"""
python3 -m src.services.ChronologicalSummary_v1.chunking_messages


"""