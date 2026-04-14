
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.engine import Engine
import pandas as pd
from src import models
from datetime import datetime
from typing import List, TypedDict




class SummaryDict(TypedDict):
    summary_from : datetime
    summary_end : datetime
    messages_count : int



def chunking_messages_by_channel(engine: Engine, session: Session, channel_id: int, min_msg: int = 50) -> List[SummaryDict]:
    """
    Funcion para chunkenizar los mensajes en intervalos de tiempo De tal forma que se tienda a haber mas de 50 mensajes por chunk
    
    """

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
    ).order_by(models.DiscordMessage.message_create_at).first()


    last_dict = summary_list[-1]
    last_message_in_df = session.query(models.DiscordMessage).filter(
        models.DiscordMessage.channel_id == channel_id,
        models.DiscordMessage.message_create_at >= last_dict['summary_from'],
        models.DiscordMessage.message_create_at <= last_dict['summary_end']
    ).order_by(models.DiscordMessage.message_create_at.desc()).first()

    summary_list[0]['summary_from'] = first_message_in_df.message_create_at
    summary_list[-1]['summary_end'] = last_message_in_df.message_create_at

    print(f"Canal {channel_id}: {len(summary_list)} particiones conseguidas.")

    return summary_list








def save_chunked_messages_by_channel(session : Session, channel_id : int, summary_list : List[SummaryDict] , min_msg : int = 50):
    print(f"Comensando a guardar mensajes del canal {channel_id}")
    summary_records = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.channel_id == channel_id
    ).order_by(models.DiscordChannelChronologicalSummary.start_time).all()

 

    # Caso 1 
    if (summary_records is None):
        print("Caso 1")
        for summ_dict in summary_list:
            record = models.DiscordChannelChronologicalSummary(
                channel_id=channel_id,
                start_time=summ_dict.get("summary_from"),
                end_time=summ_dict.get("summary_end"),
                number_messages=summ_dict.get("messages_count"),
                summary=None,
                key_words=None
            )
            session.add(record)
            
        session.commit()
        return

    last_summary_record = summary_records[-1]
    first_summary_record = summary_records[0]

    last_summary_list = summary_list[-1]
    first_summary_list = summary_list[0]



    # Caso 2
    if (last_summary_record.number_messages >= min_msg) and (last_summary_list.get("messages_count") >= min_msg):
        print("Caso 2")
        for summ_dict in summary_list:
            record = models.DiscordChannelChronologicalSummary(
                channel_id=channel_id,
                start_time=summ_dict.get("summary_from"),
                end_time=summ_dict.get("summary_end"),
                number_messages=summ_dict.get("messages_count"),
                summary=None,
                key_words=None
            )
            session.add(record)
            
        session.commit()
        return
    

    # Caso 3
    if (len(summary_list) == 1):
        print("Caso 3")
        last_summary_record.end_time = first_summary_list.get("summary_end")
        last_summary_record.number_messages = first_summary_list.get("messages_count") + last_summary_record.number_messages
        last_summary_record.summary = None
        session.add(last_summary_record)
        session.commit()
        return 
    


    # Caso 4
    if (summary_list > 1) and (len(summary_records) == 1) and (first_summary_record.number_messages < min_msg):
        print("Caso 4")
        first_summary_record.end_time = first_summary_list.get("summary_end")
        first_summary_record.number_messages = first_summary_list.get("messages_count") + first_summary_record.number_messages
        first_summary_record.summary = None
        session.add(first_summary_record)
        for i in range(1, len(summary_list)):
            summ_dict = summary_list[i]
            record = models.DiscordChannelChronologicalSummary(
                channel_id=channel_id,
                start_time=summ_dict.get("summary_from"),
                end_time=summ_dict.get("summary_end"),
                number_messages=summ_dict.get("messages_count"),
                summary=None,
                key_words=None
            )
            session.add(record)
            
        session.commit()
        return
    
    raise ValueError("Caso Desconocido")

    
    


def chunking_recursively_by_channel_id(engine: Engine, session: Session, channel_id: int, min_msg: int = 50):
    print(f"chunkenizadodo recursivamente el canal {channel_id}")
    summary_list = chunking_messages_by_channel(engine=engine, session=session, channel_id=channel_id, min_msg=min_msg)
    if summary_list is None:
        print("No hay mensajes para chunkenizar")
        return
    save_chunked_messages_by_channel(session=session, channel_id=channel_id, summary_list=summary_list)


    channels_records = session.query(models.DiscordChannel).filter_by(parent_channel_id=channel_id).all()
    print(f"hay {len(channels_records)} en channels_records") # TODO: Esto quiere decir la cantidad de hijosdel canal
    if channels_records is None:
        print(f"El canal con id {channel_id} no tiene hijos")
        return
    
    for obj in channels_records:
        chunking_recursively_by_channel_id(engine=engine, session=session, channel_id=obj.id, min_msg=min_msg)
        print("\n\n")
    


