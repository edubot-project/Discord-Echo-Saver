from rank_bm25 import BM25Okapi
import re
from typing import List, Dict
from sqlalchemy.orm import Session
from src import models


def tokenize(text: str):
    # Tokenización simple (puedes mejorarla)
    text = text.lower()
    return re.findall(r"\w+", text)


def fetch_messages_bm25(session: Session, query: str, top_k: int = 20):
    """
    Retorna los mensajes más relevantes usando BM25.

    Output:
    {
        channel_id: [
            {
                "id": message_id,
                "message_create_at": datetime,
                "score": score
            },
            ...
        ]
    }
    """

    # 1. Traer todos los mensajes
    messages = session.query(models.DiscordMessage).all()

    if not messages:
        return {}

    # 2. Crear corpus tokenizado
    corpus = [tokenize(msg.content) for msg in messages]

    # 3. Inicializar BM25
    bm25 = BM25Okapi(corpus)

    # 4. Tokenizar query
    tokenized_query = tokenize(query)

    # 5. Obtener scores
    scores = bm25.get_scores(tokenized_query)

    # 6. Ordenar por score
    ranked = sorted(
        zip(messages, scores),
        key=lambda x: x[1],
        reverse=True
    )[:top_k]

    # 7. Formatear salida
    channels: Dict[int, List] = {}

    for msg, score in ranked:
        if score <= 0:
            continue

        channel_id = msg.channel_id

        message_dict = {
            "id": msg.id,
            "message_create_at": msg.message_create_at,
            "score": float(score)
        }

        if channel_id not in channels:
            channels[channel_id] = [message_dict]
        else:
            channels[channel_id].append(message_dict)

    return channels