import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from src.database import _engine, _SessionLocal
from src.logging_config import get_logger
from src.services.v2.ChronologicalSummary.chunking_messages import (
    chunking_messages_by_channel,
    chunking_recursively_by_channel_id,
    save_chunked_messages_by_channel,
)

router = APIRouter(prefix="/chunkmessages")
logger = get_logger("api", "ChunkMessages")


class ChannelRequest(BaseModel):
    channel_id: int


@router.post("/channel", status_code=202)
async def chunk_single_channel(request: ChannelRequest):
    """
    Chunkeniza únicamente el canal indicado (sin recursividad) y guarda los
    resultados en discord_channel_chronological_summaries.
    Responde 202 de inmediato; la operación corre en segundo plano.
    """
    async def task():
        session = _SessionLocal()
        try:
            def _run():
                summary_list = chunking_messages_by_channel(
                    engine=_engine,
                    session=session,
                    channel_id=request.channel_id,
                )
                if summary_list:
                    save_chunked_messages_by_channel(
                        session=session,
                        channel_id=request.channel_id,
                        summary_list=summary_list,
                    )

            await asyncio.to_thread(_run)
        except Exception as e:
            logger.error(f"Error en POST /chunkmessages/channel: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {"status": "accepted", "channel_id": request.channel_id}


@router.post("/channel/recursive", status_code=202)
async def chunk_channel_recursive(request: ChannelRequest):
    """
    Chunkeniza el canal indicado y todos sus hijos recursivamente, guardando
    los resultados en discord_channel_chronological_summaries.
    Responde 202 de inmediato; la operación corre en segundo plano.
    """
    async def task():
        session = _SessionLocal()
        try:
            await asyncio.to_thread(
                chunking_recursively_by_channel_id,
                _engine,
                session,
                request.channel_id,
            )
        except Exception as e:
            logger.error(f"Error en POST /chunkmessages/channel/recursive: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {"status": "accepted", "channel_id": request.channel_id}
