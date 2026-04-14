# from langchain_core.embeddings.embeddings import Embeddings

from sqlalchemy.orm import Session
from src import models

from google import genai
import asyncio
from typing import List
from src import models


async def embed_single_batch_google(session : Session, semaphore : asyncio.Semaphore, client : genai.Client, model : str, batch : List[models.DiscordChannelChronologicalSummary]):
    BATCH_SIZE = 100 # la api de google solo puede embeber 100 chuns a la vez
    async with semaphore:
        try:
            contents = [r.summary for r in batch]
            result = client.models.embed_content(
                model=model,
                contents=contents
            )

            n = 0
            for embedding in result.embeddings:
                vec = embedding.values
                record = batch[n]
                record.summary_embedding = vec
                session.add(record)
                n += 1
            
            session.commit()
        except Exception as e:
            print(f"Error : {e}")




def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]




if __name__ == "__main__":

    chunks = [i for i in range(3)]
    for batch_idx, batch in enumerate(chunk_list(lst=chunks, chunk_size=5)):
        print(f"batch {batch_idx + 1} -- {batch}")

    pass
                                      

    

"""
python3 -m src.services.ChronologicalSummary_v1.embeddings



"""