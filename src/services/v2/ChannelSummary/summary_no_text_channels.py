from src import discord_models as models
from .prompt import SUMMARY_FORUM_OR_CATEGORY_CHANNEL_PROMPT_3

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.orm import Session
from typing import TypedDict, List, Dict, Any

import asyncio

from src.logging_config import get_logger
logger = get_logger(module_name="summary_text", DIR="ChannelSummary_v2")




def collect_all_channels_summaries_by_channel(session: Session, channel_id: int):

    summary_records = (
        session.query(
            models.DiscordChannel.id,
            models.DiscordChannel.name,
            models.DiscordChannelSummary.summary
        )
        .join(
            models.DiscordChannelSummary,
            models.DiscordChannelSummary.channel_id == models.DiscordChannel.id
        )
        .filter(models.DiscordChannel.id == channel_id)
        .all()
    )

    # summary_records = [(id, name, summary), (id, name, summary), ...]

    if not summary_records:
        print(f"No hay resúmenes para el canal con id {channel_id}.")
        return

    # results = [
    #     {"id": r[0], "name": r[1], "summary": r[2]}
    #     for r in summary_records
    # ]

    template = "--- \n\n Nombre del canal: {channel_name} \n\n Resemun del canal: \n\n {summary} \n\n\n"
    channels_summaries = ""

    for item in summary_records:
        channels_summaries += template.format(channel_name=item[1], summary=item[2])
    
    return channels_summaries






class PendingSummaryPrompt(TypedDict):
    prompt : str
    cronological_summary_lenght : int
    channel_id : int
    

def collect_all_pending_category_or_forum_summaries_prompts(session : Session, root_id : int) -> List[PendingSummaryPrompt]:

    all_tasks = []

    channel_record = session.query(models.DiscordChannel).filter_by(id=root_id).first()
    if channel_record is None:
        print(f"el canal con id {root_id} no existe")
        return
    
    
    if channel_record.channel_type not in {"forum", "category"}:
        print(f"El canal con id {root_id} es un canal de texto o hilo, saltando ...")
        return
    
    
    channels_summaries = collect_all_channels_summaries_by_channel(session=session, channel_id=root_id)

    prompt = SUMMARY_FORUM_OR_CATEGORY_CHANNEL_PROMPT_3.format(discord_channel=channel_record.name, channels_summaries=channels_summaries)

    all_tasks.append({"prompt":prompt, "idx":channel_record.id})

    channels_childs = session.query(models.DiscordChannel).filter(
        models.DiscordChannel.parent_channel_id == root_id,
        models.DiscordChannel.channel_type.in_({"forum", "category"})
    ).all()

    



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

