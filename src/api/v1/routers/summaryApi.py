import asyncio
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from src import settings
from src.database import _SessionLocal
from src.logging_config import get_logger
from src.services.v2.ChronologicalSummary.summary import process_parallel_system
from src.services.v2.ChronologicalSummary.summary_ollama_server import (
    process_parallel_system as process_parallel_system_ollama,
)

router = APIRouter(prefix="/summary")
logger = get_logger("api", "SummaryApi")


class ChannelRequest(BaseModel):
    channel_id: int


class OllamaChannelRequest(BaseModel):
    channel_id: int
    ollama_urls: List[str] = ["http://10.8.0.11:11434", "http://10.8.0.11:11435"]
    model: str = "gemma3:27b"


@router.post("/channel", status_code=202)
async def summarize_channel(request: ChannelRequest):
    """
    Genera resúmenes en paralelo para todos los chunks pendientes (summary IS NULL)
    del canal indicado y sus hijos recursivamente.
    Responde 202 de inmediato; la operación corre en segundo plano.
    """
    async def task():
        session = _SessionLocal()
        try:
            llm = ChatGroq(
                model="openai/gpt-oss-120b",
                temperature=0.2,
                api_key=settings.GROQ_API_KEY,
            )
            semaphore = asyncio.Semaphore(3)
            await process_parallel_system(
                session=session,
                semaphore=semaphore,
                llm=llm,
                root_idx=request.channel_id,
            )
        except Exception as e:
            logger.error(f"Error en POST /summary/channel: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {"status": "accepted", "channel_id": request.channel_id}


@router.post("/channel/ollama", status_code=202)
async def summarize_channel_ollama(request: OllamaChannelRequest):
    """
    Genera resúmenes en paralelo usando instancias de Ollama distribuidas entre
    las URLs indicadas (round-robin por GPU). Solo procesa chunks con summary IS NULL.
    Responde 202 de inmediato; la operación corre en segundo plano.
    """
    async def task():
        session = _SessionLocal()
        try:
            llm_endpoints = [
                ChatOllama(model=request.model, temperature=0.3, base_url=url)
                for url in request.ollama_urls
            ]
            # 2 slots por GPU, igual que el bloque __main__ del servicio
            semaphore = asyncio.Semaphore(len(llm_endpoints) * 2)
            await process_parallel_system_ollama(
                session=session,
                semaphore=semaphore,
                llm_endpoints=llm_endpoints,
                root_idx=request.channel_id,
            )
        except Exception as e:
            logger.error(f"Error en POST /summary/channel/ollama: {e}")
        finally:
            session.close()

    asyncio.create_task(task())
    return {
        "status": "accepted",
        "channel_id": request.channel_id,
        "model": request.model,
        "ollama_urls": request.ollama_urls,
    }
