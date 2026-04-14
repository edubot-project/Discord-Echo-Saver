import asyncio
from sqlalchemy.orm import Session
from src import models
from datetime import datetime

from langchain_core.language_models.chat_models import BaseChatModel
from src.services.ChronologicalSummary_v1.prompts import SUMMARY_DISCORD_MESSAGES_1


import re
from sqlalchemy.orm import Session
from src import models
from datetime import datetime

from src.logging_config import get_logger
logger = get_logger(module_name="summaery", DIR="ChronologicalSummary_v1")


def get_messages(session: Session, channel_id: int, summary_from: datetime, summary_end: datetime):
    # 1. Recuperar todos los mensajes del rango de una sola vez
    message_content_records = session.query(models.DiscordMessage).filter(
        models.DiscordMessage.channel_id == channel_id,
        models.DiscordMessage.message_create_at >= summary_from,
        models.DiscordMessage.message_create_at <= summary_end
    ).order_by(models.DiscordMessage.message_create_at.asc()).all()

    if not message_content_records:
        return ""

    # 2. Crear un mapa de UserID -> Name y MessageID -> MessageRecord
    # Esto evita consultas repetitivas a la base de datos (N+1)
    user_map = {str(msg.user_id): msg.user_name for msg in message_content_records}
    msg_map = {msg.id: msg for msg in message_content_records}

    # 3. Función para reemplazar menciones <@ID> por @Nombre
    def replace_mentions(text, mapping):
        if not text: return ""
        # Busca el patrón <@números>
        return re.sub(r'<@!?(\d+)>', lambda m: f"@{mapping.get(m.group(1), 'usuario_desconocido')}", text)

    # Plantillas optimizadas
    TEMPLATE_1 = "User: {user_name}  | Date: {date}\nContent: {content}\n\n" # (ID: {user_id})
    TEMPLATE_2 = "User: {user_name}  | Date: {date} | Reply to: {reply_to_name}\nContent: {content}\n\n" # (ID: {user_id})

    final_transcript = []

    for obj in message_content_records:
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


async def process_single_chunk(llm : BaseChatModel, prompt : str, idx : int, semaphore : asyncio.Semaphore):
    print("\n")
    print("****** precess_single_chunk")
    async with semaphore:
        try:
            ai_message = await llm.ainvoke(prompt)
            print(f"usage_metadata: {ai_message.usage_metadata} \n\n")
            return {"summary": ai_message.content, "usage_metadata":ai_message.usage_metadata, "idx":idx}
        except Exception as e:
            logger.info(f"error procesando en el registro {idx} de DiscordChannelChronologicalSummary: \n {e} \n\n")
            return None



async def asummary_all_chunks(session : Session, semaphore : asyncio.Semaphore, llm : BaseChatModel):

    print(">>> entrando a main_1")
    input_tokens = 0
    output_tokens = 0

    chronological_summary_records = session.query(models.DiscordChannelChronologicalSummary).filter(models.DiscordChannelChronologicalSummary.summary.is_(None)).all()
    print(f">>> registros encontrados: {len(chronological_summary_records)}")
    if len(chronological_summary_records) == 0:
        print(">>> NO HAY NADA PARA PROCESAR")
        return
    
    prompts = []
    for obj in chronological_summary_records:
        messages = get_messages(session=session, channel_id=obj.channel_id, summary_from=obj.start_time, summary_end=obj.end_time)
        print("\n"*4)
        prompt = SUMMARY_DISCORD_MESSAGES_1.format(messages=messages)
        prompts.append({'prompt':prompt, 'idx':obj.id})
    
    tasks = [process_single_chunk(llm=llm, prompt=p['prompt'], idx=p['idx'], semaphore=semaphore) for p in prompts]
    results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            db_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=r["idx"]).first()
            db_record.summary = r["summary"]
            input_tokens += r["usage_metadata"].get("input_tokens", 0)
            output_tokens += r["usage_metadata"].get("output_tokens", 0)
            session.add(db_record)
    
    session.commit()
    session.close()
    print("\n\n")
    print(f"input_tokens: {input_tokens} | output_tokens: {output_tokens}")




async def summmary_by_channel_id(session : Session, semaphore : asyncio.Semaphore, llm : BaseChatModel, idx : int):
    print(f"======== summmary_by_channel_id --- procesando el canal con id {idx}")
    input_tokens = 0
    output_tokens = 0

    channel_record = session.query(models.DiscordChannel).filter_by(id=idx).first() 
    if channel_record is None:
        print(f"No existe canal con este id: {idx}")
        return None
    
    if channel_record.channel_type in {"forum", "thread"}:
        print("El tipo de canal es foro o categoria. Saltandolo, no contienen mensajes")
        return None
    
    print("El canal es de tipo texto o hilo consiguiendo los resumenes")
    summary_records = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.channel_id == idx,
        models.DiscordChannelChronologicalSummary.summary.is_(None),
    ).order_by(models.DiscordChannelChronologicalSummary.start_time).all()
    if summary_records is None:
        print(f"No hay resumens pendientes en el canal {idx}")
    
    datos = []
    for obj in summary_records:
        messages = get_messages(session, channel_id=idx, summary_from=obj.start_time, summary_end=obj.end_time)
        print(f"mensajes conseguidos del canal desde {obj.start_time.strftime('%d/%m/%Y %H:%M')} hasta {obj.end_time.strftime('%d/%m/%Y %H:%M')}")
        prompt = SUMMARY_DISCORD_MESSAGES_1.format(messages=messages)
        datos.append({"prompt":prompt, "idx":obj.id})
    
    tasks = [
        process_single_chunk(llm=llm, prompt=d["prompt"], idx=d["idx"], semaphore=semaphore)
        for d in datos
    ]

    result = await asyncio.gather(*tasks)

    for r in result:
        if r:
            db_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=r['idx']).first()
            db_record.summary = r["summary"]
            input_tokens += r["usage_metadata"].get("input_tokens", 0)
            output_tokens += r["usage_metadata"].get("output_tokens", 0)
            session.add(db_record)
    
    session.commit()
    print(f"input_tokens: {input_tokens} | output_tokens: {output_tokens}")





async def summarize_recursively_by_channel_id(session : Session, semaphore : asyncio.Semaphore, llm : BaseChatModel, idx : int):

    await summmary_by_channel_id(session=session, semaphore=semaphore, llm=llm, idx=idx)

    channel_records = session.query(models.DiscordChannel).filter(
        models.DiscordChannel.parent_channel_id == idx
    ).all()


    for obj in channel_records:
        await summarize_recursively_by_channel_id(session=session, semaphore=semaphore, llm=llm, idx=obj.id)
        print("\n"*5)





def redo_summary(session : Session, llm : BaseChatModel, summary_id : int):
    summary_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=summary_id).first()
    pass








if __name__=="__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src import settings
    from src import models
    from datetime import datetime
    import asyncio 

    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_ollama import ChatOllama
    from langchain_groq import ChatGroq

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()

    semaphore = asyncio.Semaphore(5)



    start = datetime.strptime('2025-03-31 00:00:00', '%Y-%m-%d %H:%M:%S')
    end = datetime.strptime('2025-05-11 23:59:59', '%Y-%m-%d %H:%M:%S')

    
    # messages = get_messages(session=session, channel_id=1357437165738393822, summary_from=start, summary_end=end)
    # print(messages)

    semaphore = asyncio.Semaphore(2)
    # model = "gemini-2.0-flash"
    # llm = ChatGoogleGenerativeAI(model=model, temperature=0.5, google_api_key=settings.GOOGLE_API_KEY)
    
    # model = "gpt-oss:20b"
    # llm = ChatOllama(model=model, temperature=0.3, base_url=settings.SERVER_AI_TEAM)

    model="openai/gpt-oss-120b"
    llm = ChatGroq(model=model, temperature=0.2, api_key=settings.GROQ_API_KEY)

    # asyncio.run(
    #     asummary_all_chunks(session=session, semaphore=semaphore, llm=llm)
    # )

    asyncio.run(
        summarize_recursively_by_channel_id(session=session, semaphore=semaphore, llm=llm, idx=1309953285582491649)
    )






"""
python3 -m src.services.ChronologicalSummary_v1.summary


"""