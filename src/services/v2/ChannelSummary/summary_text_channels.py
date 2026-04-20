from src import models
from .prompt import SUMMARY_TEXT_CHANNEL_PROMPT_3

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.orm import Session
from typing import TypedDict, List, Dict, Any

import asyncio

from src.logging_config import get_logger
logger = get_logger(module_name="summary_text", DIR="ChannelSummary_v2")




def collect_all_chronological_summaries_by_channel(session : Session, channel_id : int):

    summary_records = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.channel_id == channel_id,
        models.DiscordChannelChronologicalSummary.summary.is_not(None)
    ).order_by(models.DiscordChannelChronologicalSummary.start_time).all()

    if summary_records is None:
        print(f"No hay resumenes del canal {channel_id}. Puede que el canal sea un foro o categoria o que no existan resumenes cronologicos del canal de texto o hilo")
        return
    
    cronological_summary_lenght = len(summary_records)

    template = "Resumen desde {start_time} hasta {end_time} \n\n Resumen: \n {summary} \n\n\n\n"
    channel_summary = ""

    for obj in summary_records:
        channel_summary += template.format(
            start_time=obj.start_time.strftime("%d/%m/%Y %H:%M"),
            end_time=obj.end_time.strftime("%d/%m/%Y %H:%M"),
            summary=obj.summary
        )
    

    return {"channel_summary":channel_summary, "cronological_summary_lenght":cronological_summary_lenght}




class PendingSummaryPrompt(TypedDict):
    prompt : str
    cronological_summary_lenght : int
    channel_id : int
    

def collect_all_pending_channel_summaries_prompts(session : Session, root_id : int) -> List[PendingSummaryPrompt]:

    all_tasks = []

    channel_record = session.query(models.DiscordChannel).filter_by(id=root_id).first()
    if channel_record is None:
        print(f"el canal con id {root_id} no existe")
        return
    
    channel_name = channel_record.name
    
    if channel_record.channel_type in {"forum", "category"}:
        print(f"El canal con id {root_id} es una categoria o un foro, saltando ...")
        return
    
    channel_dict = collect_all_chronological_summaries_by_channel(session=session, channel_id=root_id)

    channel_summary = channel_dict["channel_summary"]
    cronological_summary_lenght = channel_dict["cronological_summary_lenght"]

    prompt = SUMMARY_TEXT_CHANNEL_PROMPT_3.format(channel_name=channel_name, channel_summary=channel_summary)

    all_tasks.append({"prompt":prompt, "cronological_summary_lenght":cronological_summary_lenght, "channel_id":root_id})

    child_channels = session.query(models.DiscordChannel).filter(
        models.DiscordChannel.parent_channel_id == root_id
    ).all()

    if child_channels is None:
        print(f"El canal {root_id} no tiene hijos")

    for child in child_channels:
        child_task = collect_all_pending_channel_summaries_prompts(session=session, root_id=child.id)
        if child_task is not None:
            all_tasks = all_tasks + child_task
    
    return all_tasks




class ProcessResponse(TypedDict):
    usage_metadata : Dict[str, Any]
    summary : str
    idx : int
    cronological_summary_lenght : int

    pass

async def process_single_chunk(llm : BaseChatModel, semaphore : asyncio.Semaphore, pending_dict : PendingSummaryPrompt) -> ProcessResponse:
    print("\n")
    print("****** precess_single_chunk")
    async with semaphore:
        try:
            prompt = pending_dict.get("prompt")
            idx = pending_dict.get("channel_id")
            ai_message = await llm.ainvoke(prompt)
            print(f"usage_metadata: {ai_message.usage_metadata}, \n\n numero de caracteres: {len(ai_message.content)} \n\n\n")
            return {"summary": ai_message.content, "usage_metadata":ai_message.usage_metadata, "idx":idx, "cronological_summary_lenght":pending_dict.get("cronological_summary_lenght")}
        except Exception as e:
            logger.info(f"error procesando en el registro {idx} de DiscordChannelChronologicalSummary: \n {e} \n\n")
            return None





async def procces_all_peding_text_channel_summaries(session : Session, semaphore : asyncio.Semaphore, llm : BaseChatModel, root_id : int):
    pending_dicts = collect_all_pending_channel_summaries_prompts(session=session, root_id=root_id)

    tasks = [
        process_single_chunk(
            llm=llm, semaphore=semaphore, pending_dict=d
        )
        for d in pending_dicts
    ]
    
    result = await asyncio.gather(*tasks)

    input_tokens, output_tokens = 0, 0
    count = 0

    for r in result:
        if r is not None:
            record = models.DiscordChannelSummary(
                channel_id=r.get("idx"),
                summary=r.get("summary"),
                cronological_summary_lenght=r.get("cronological_summary_lenght"),
            )
            session.add(record)
            meta = r.get("usage_metadata")
            if meta:
                input_tokens += meta.get("input_tokens", 0)
                output_tokens += meta.get("output_tokens", 0)
            
            count += 1
    session.commit()

    print(f"\n--- ✨ ¡PROCESO FINALIZADO!")
    print(f"--- 📊 Resúmenes guardados: {count}")
    print(f"--- 📊 Tokens totales: In: {input_tokens} | Out: {output_tokens}")
            







def make_channel_summary(session : Session, channel_id :int, llm : BaseChatModel):

    chrnological_summary = collect_all_chronological_summaries_by_channel(session=session, channel_id=channel_id)

    channel_summary = chrnological_summary["channel_summary"]
    cronological_summary_lenght = chrnological_summary["cronological_summary_lenght"]

    channel = session.query(models.DiscordChannel).filter_by(id=channel_id).first()
    if channel is None:
        print(f"El canal con id {channel_id} No se encuentra")
    
    prompt = SUMMARY_TEXT_CHANNEL_PROMPT_3.format(
        channel_name=channel.name,
        channel_summary=channel_summary
    )

    ai_response = llm.invoke(prompt)

    print(f"usage_metadata: {ai_response.usage_metadata}")

    record = models.DiscordChannelSummary(
        channel_id=channel_id,
        summary=ai_response.content,
        cronological_summary_lenght=cronological_summary_lenght
    )

    session.add(record)
    session.commit()

