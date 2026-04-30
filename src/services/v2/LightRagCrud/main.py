from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from .crud3 import delete_in_lightrag_status, insert_to_light_rag, sweep_pending_deletions, get_pending_track_ids, sync_processed_lightrag_docs
from ..ChronologicalSummary.summary2 import make_all_pending_summaries
from src import discord_models as dmodels

from langchain_core.language_models.chat_models import BaseChatModel

import asyncio
import time




def prune_in_lightrag_status_from_summaries(session : Session):
    summary_records = session.query(dmodels.DiscordChannelChronologicalSummary).filter(
        dmodels.DiscordChannelChronologicalSummary.status == "in_lightrag",
        dmodels.DiscordChannelChronologicalSummary.summary.is_(None),
    ).all()

    if summary_records is None:
        print("No hay registros en summary_records")
        return None

    print(f"Hay {len(summary_records)} registros para borrrar en el servicio de lightrag")

    summary_ids = []
    for obj in summary_records:
        summary_ids.append(obj.id)

    delete_in_lightrag_status(session=session, summary_ids=summary_ids)





def partition_summary(session : Session, max_msg : int = 100):
    summary_records = session.query(dmodels.DiscordChannelChronologicalSummary).filter(
        dmodels.DiscordChannelChronologicalSummary.status == None
    ).all()

    if summary_records is None:
        print("summary_records es None")
        return None

    for obj in summary_records:
        if obj.number_messages >= max_msg:
            print(f"Particionando summary con id {obj.id} del canal con id {obj.channel_id}")
            messages_records = session.query(dmodels.DiscordMessage).filter(
                dmodels.DiscordMessage.channel_id == obj.channel_id,
                dmodels.DiscordMessage.message_create_at >= obj.start_time,
                dmodels.DiscordMessage.message_create_at <= obj.end_time,
            ).order_by(dmodels.DiscordMessage.message_create_at).all()

            if len(messages_records) < 2:
                print("messages_records < 2 saltando")
                continue

            mid = len(messages_records) // 2
            first_half = messages_records[:mid]
            second_half = messages_records[mid:]

            obj.end_time = first_half[-1].message_create_at
            obj.number_messages = len(first_half)

            new_summary = dmodels.DiscordChannelChronologicalSummary(
                channel_id=obj.channel_id,
                start_time=second_half[0].message_create_at,
                end_time=second_half[-1].message_create_at,
                number_messages=len(second_half),
                status=None,
            )
            session.add(new_summary)

    session.commit()








if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from langchain_groq import ChatGroq

    from src import discord_models as dmodels
    from src import lighrag_models as lmodels

    from src import settings
    import asyncio

    from src.logging_config import setup_base_logging

    setup_base_logging()
    

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()




    # prune_in_lightrag_status_from_summaries(session=session)

    # ========================================================
    # ========================================================

    sweep_pending_deletions(session=session)

    # ========================================================
    # ========================================================


    # partition_summary(session=session)


    # ========================================================
    # ========================================================
    

    # semaphore = asyncio.Semaphore(3)
    # model = "openai/gpt-oss-120b"
    # llm = ChatGroq(model=model, temperature=0.2, api_key=settings.GROQ_API_KEY)
    # asyncio.run(
    #     make_all_pending_summaries(session=session, semaphore=semaphore, llm=llm)
    # )


    # ========================================================
    # ========================================================
    

    # summary_records = session.query(dmodels.DiscordChannelChronologicalSummary).filter(
    #     dmodels.DiscordChannelChronologicalSummary.summary.is_not(None), # Esto quizas sea redundante porque si el status es readt entonces el campo summary es no vacio
    #     dmodels.DiscordChannelChronologicalSummary.status == "ready"
    # ).all()

    # for obj in summary_records:
    #     insert_to_light_rag(session=session, summary_id=obj.id, channel_id=obj.channel_id, start_time=obj.start_time, end_time=obj.end_time, summary=obj.summary)
    #     # session.commit()
    #     print("\n\n")
    #     time.sleep(0.5)

    # ========================================================
    # ========================================================

    # ids = get_pending_track_ids(session=session)

    # print(len(ids))

    # sync_processed_lightrag_docs(session=session, track_ids=ids)


    # ========================================================
    # ========================================================


    # engine2 = create_engine(settings.LIGHTRAG_CONN_STRING)
    # MySession2 = sessionmaker(bind=engine2)
    # session2 = MySession2()

    # d_records = session.query(dmodels.LightRagDocs).filter(
    #     dmodels.LightRagDocs.lightrag_doc_id.is_(None)
    # ).all()

    # for obj in d_records:
    #     r = session2.query(lmodels.LightRagDocStatus).filter(
    #         lmodels.LightRagDocStatus.track_id == obj.lightrag_track_id
    #     ).first()

    #     session2.delete(r)
    # session2.commit()



    


"""
python3 -m src.services.v2.LightRagCrud.main


"""




    