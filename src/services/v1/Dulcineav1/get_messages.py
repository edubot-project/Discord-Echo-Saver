import asyncio
from sqlalchemy.orm import Session
from src import models
from datetime import datetime

from langchain_core.language_models.chat_models import BaseChatModel

import re
from sqlalchemy.orm import Session
from src import models
from datetime import datetime

from typing import Dict, List, TypedDict
from datetime import timedelta
from sqlalchemy import or_



# from src.logging_config import get_logger
# logger = get_logger(module_name="summaery", DIR="ChronologicalSummary_v1")


class MessagesKeyWord(TypedDict):
    message_id : int
    message_create_at : datetime



# TODO: filtrar por el foro de solenium
def fetch_messages_by_keyword(session: Session, key_word: str) -> Dict[int, MessagesKeyWord]:
    """
    Recupera los registros de DiscordMessages cuyo content contenga `key`.

    Retorna un diccionario asi:

    {
        channel_id : [{message_id : id, message_create_at : datetime} ... ]
        ...generate_partial_response
    }
    """

    messages_records = session.query(models.DiscordMessage).filter(
        models.DiscordMessage.content.ilike(f'%{key_word}%')
    ).all()

    
    channels : Dict[int, List] = {}
    for msg in messages_records:
        channel_id = msg.channel_id
        message_create_at = msg.message_create_at
        message_id = msg.id
        message_dict = {"message_create_at":message_create_at, "id":message_id}

        if channel_id not in channels:
            channels[channel_id] = [message_dict]
        else:
            channels[channel_id].append(message_dict)
    
    return channels





def merge_message(session : Session, channel_id : int, messages_date : List[datetime], days : int = 7):
    if not messages_date:
        return []
    
    # Construir condiciones OR para cada fecha
    conditions = []
    for date in messages_date:
        start_date = date - timedelta(days=days)
        end_date = date + timedelta(days=days)
        conditions.append(
            models.DiscordMessage.message_create_at.between(start_date, end_date)
        )
    
    # Una sola consulta
    messages_record = session.query(models.DiscordMessage).filter(
        models.DiscordMessage.channel_id == channel_id,
        or_(*conditions)
    ).order_by(models.DiscordMessage.message_create_at).all()
    
    return messages_record    





# Función para reemplazar menciones <@ID> por @Nombre
def replace_mentions(text, mapping):
    if not text: return ""
    # Busca el patrón <@números>
    return re.sub(r'<@!?(\d+)>', lambda m: f"@{mapping.get(m.group(1), 'usuario_desconocido')}", text)





def get_format_messages(messages_records : List[models.DiscordMessage]):
    
    # Crear un mapa de UserID -> Name y MessageID -> MessageRecord
    # Esto evita consultas repetitivas a la base de datos (N+1)
    user_map = {str(msg.user_id): msg.user_name for msg in messages_records}
    msg_map = {msg.id: msg for msg in messages_records}

    TEMPLATE_1 = "User: {user_name}  | Date: {date}\nContent: {content}\n\n" # (ID: {user_id})
    TEMPLATE_2 = "User: {user_name}  | Date: {date} | Reply to: {reply_to_name}\nContent: {content}\n\n" # (ID: {user_id})

    final_transcript = []

    for obj in messages_records:
        try:
            # Limpiar el contenido reemplazando IDs por nombres
            clean_content = replace_mentions(obj.content, user_map)
            date_str = obj.message_create_at.strftime("%d/%m/%Y %H:%M")
            
            # Lógica de respuesta
            if obj.reply_to:
                # Intentamos buscar el nombre en nuestro mapa local primero
                parent_msg = msg_map.get(obj.reply_to)
                if parent_msg:
                    reply_name = parent_msg.user_name
                else:
                    # Si la respuesta es a un mensaje fuera de este rango de tiempo,
                    # podrías hacer una consulta rápida o poner "mensaje previo"
                    reply_name = "usuario_en_hilo_anterior"
                
                msg_text = TEMPLATE_2.format(
                    user_name=obj.user_name,
                    #user_id=obj.user_id,
                    date=date_str,
                    reply_to_name=reply_name,
                    content=clean_content
                )
            else:
                msg_text = TEMPLATE_1.format(
                    user_name=obj.user_name,
                    #user_id=obj.user_id,
                    date=date_str,
                    content=clean_content
                )
            
            final_transcript.append(msg_text)

        except Exception as e:
            print(f"Error procesando mensaje {obj.id}: {e}")
        
    return "".join(final_transcript)






def get_channel_name(session: Session, channel_id: int) -> str | None:
    """
    Retrieves the name of a channel given its ID.
    """
    channel_record = (
        session.query(models.DiscordChannel).filter_by(id=channel_id).first()
    )
    if channel_record:
        return channel_record.name
    return None





if __name__=="__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src import settings

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()

    key_word = "COLBOYT123P1"
    messages_dict = fetch_messages_by_keyword(session=session, key_word=key_word)

    print(f"messages_dict: \n {messages_dict} \n\n")

    first_key_in_messages_dict = list(messages_dict.keys())[0] 
    print(f"first_key_in_messages_dict: {first_key_in_messages_dict} \n\n")


    messages_date = []
    for dic in messages_dict.get(first_key_in_messages_dict):
        print(dic)
        messages_date.append(dic.get("message_create_at"))
    

    messages_records = merge_message(session=session, channel_id=first_key_in_messages_dict, messages_date=messages_date)
    print(f"Hay {len(messages_records)} elementos en messages_records \n\n")

    messages = get_format_messages(messages_records=messages_records)

    print(messages)

    












"""
python3 -m src.services.Dulcineav1.get_messages


"""
