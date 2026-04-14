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





async def collect_all_pending_summaries(session: Session, channel_id: int):
    """
    Recorre la jerarquía y devuelve una lista plana de todos los prompts pendientes.
    Esto evita procesar canal por canal y permite paralelismo real.
    """
    all_tasks = []

    # 1. Obtener registros pendientes del canal actual
    summary_records = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.channel_id == channel_id,
        models.DiscordChannelChronologicalSummary.summary.is_(None),
    ).order_by(models.DiscordChannelChronologicalSummary.start_time).all()

    for obj in summary_records:
        messages = get_messages(session, channel_id=channel_id, summary_from=obj.start_time, summary_end=obj.end_time)
        if messages:
            prompt = SUMMARY_DISCORD_MESSAGES_1.format(messages=messages)
            all_tasks.append({"prompt": prompt, "idx": obj.id})
    
    # 2. Buscar canales hijos (recursividad para recolectar, no para procesar)
    child_channels = session.query(models.DiscordChannel).filter(
        models.DiscordChannel.parent_channel_id == channel_id
    ).all()

    for child in child_channels:
        # Llamada recursiva para seguir recolectando
        child_tasks = await collect_all_pending_summaries(session, child.id)
        all_tasks.extend(child_tasks)

    return all_tasks

async def process_parallel_system(session: Session, semaphore: asyncio.Semaphore, llm: BaseChatModel, root_idx: int):
    """
    Orquestador principal que recolecta todo y lo lanza a las GPUs.
    """
    print(f"--- 🔍 Recolectando tareas pendientes desde el ID {root_idx}...")
    
    # Recolectamos TODO primero
    pending_tasks_data = await collect_all_pending_summaries(session, root_idx)
    
    if not pending_tasks_data:
        print("--- ✅ No hay resúmenes pendientes.")
        return

    print(f"--- 🚀 Lanzando {len(pending_tasks_data)} tareas a las GPUs...")

    # Creamos las corrutinas
    tasks = [
        process_single_chunk(llm=llm, prompt=t["prompt"], idx=t["idx"], semaphore=semaphore)
        for t in pending_tasks_data
    ]

    # Aquí ocurre la magia: asyncio.gather lanzará tantas como el semáforo permita
    results = await asyncio.gather(*tasks)

    # Guardado de resultados
    print("--- 💾 Guardando resultados en DB...")
    input_tokens, output_tokens = 0, 0
    
    for r in results:
        if r:
            db_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=r['idx']).first()
            if db_record:
                db_record.summary = r["summary"]
                input_tokens += r["usage_metadata"].get("input_tokens", 0)
                output_tokens += r["usage_metadata"].get("output_tokens", 0)
                session.add(db_record)
    
    session.commit()
    print(f"--- ✨ Finalizado | Tokens In: {input_tokens} | Tokens Out: {output_tokens}")





# --- En tu bloque __main__ ---
if __name__=="__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src import settings
    from src import models
    from datetime import datetime
    import asyncio 

    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_ollama import ChatOllama

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()

    semaphore = asyncio.Semaphore(2)
    # ... (tu setup anterior)

    #model = "gpt-oss:20b"
    model = "qwen3:30b"
    llm = ChatOllama(model=model, temperature=0.3, base_url=settings.SERVER_AI_TEAM)


    # CONFIGURACIÓN CLAVE:
    # Como en Ollama pusiste NUM_PARALLEL=4, aquí el semáforo debe ser 4.
    # Si quieres que Python siempre tenga una petición "en cola" lista para entrar
    # cuando una GPU se libere, podrías probar con 5 o 6.
    semaphore = asyncio.Semaphore(4) 
    

    asyncio.run(
        process_parallel_system(session=session, semaphore=semaphore, llm=llm, root_idx=1309953285582491649)
    )

    
"""
python3 -m src.services.ChronologicalSummary_v1.summary_ollama


"""