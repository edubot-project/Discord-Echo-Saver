from sqlalchemy.orm import Session
from src import settings
from src import discord_models as models
from src import lighrag_models as Lmodels
from typing import List
import httpx
import logging

logger = logging.getLogger(__name__)


LIGHTRAG_URL = f"http://{settings.LIGHTRAG_SERVER_HOST}:{settings.LIGHTRAG_SERVER_PORT}"
HEADERS = {}



from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import settings
import asyncio


engine = create_engine(settings.LIGHTRAG_CONN_STRING)
MySession2 = sessionmaker(bind=engine)
session2 = MySession2()

                                                                                                            
import time                                                                                                                                                                           
                                                                                                                                                                                    
def _wait_until_deleted(doc_id: str, timeout: int = 120, poll_interval: int = 3):                                                                                                     
    """Polling sobre la DB de LightRAG hasta que el doc_id ya no exista."""                                                                                                           
    deadline = time.time() + timeout                                                                                                                                                  
    while time.time() < deadline:
        session2.expire_all()  # fuerza re-lectura, evita caché de sqlalchemy                                                                                                         
        still_exists = session2.query(Lmodels.LightRagDocStatus).filter_by(id=doc_id).first()                                                                                         
        if still_exists is None:                                                                                                                                                      
            return                                                                                                                                                                    
        time.sleep(poll_interval)                                                                                                                                                     
    raise TimeoutError(f"LightRAG no terminó de borrar el doc {doc_id} en {timeout}s")




def delete_in_lightrag_status(session: Session, summary_id: int):                                                                                                                     
    record = session.query(models.LightRagDocs).filter_by(summary_id=summary_id).first()
    if record is None:                                                                                                                                                                
        raise ValueError(f"El summary_id {summary_id} no está en lightrag_docs")
                                                                                                                                                                                    
    doc_id = record.lightrag_doc_id
                                                                                                                                                                                    
    payload = { 
        "doc_ids": [doc_id],
        "delete_file": True,
        "delete_llm_cache": False,
    }
                                                                                                                                                                                    
    with httpx.Client() as client:
        response = client.delete(                                                                                                                                                     
            f"{LIGHTRAG_URL}/documents/delete_document",
            json=payload,
            headers=HEADERS,
            timeout=120,
        )
        if not response.is_success:
            logger.warning(                                                                                                                                                           
                "LightRAG delete request failed for summary_id=%s: status=%s body=%s",
                summary_id, response.status_code, response.text,                                                                                                                      
            )   
            return None                                                                                                                                                               
                
        data = response.json()                                                                                                                                                        
        print(f"Borrado iniciado en LightRAG: {data}")
                                                                                                                                                                                    
    # Espera a que LightRAG confirme el borrado en su propia DB                                                                                                                       
    _wait_until_deleted(doc_id)
                                                                                                                                                                                    
    session.delete(record)
    session.commit()
    print(f"Registro eliminado de lightrag_docs para summary_id={summary_id}")   





# def delete_in_lightrag_status(session : Session, summary_id : int):  
#     """
#     dado un registro de DiscordChannelChronologicalSummary que ya estaba en lightrag (status = in_lightrag) este lo elimina de lightrag y luego lo elimina de LightRagDocs
    
#     """  
#     record = session.query(models.LightRagDocs).filter_by(
#         summary_id=summary_id
#     ).first()
#     if record is None:
#         raise ValueError(f"Error. el summary_id {summary_id} no esta en el modelo lightrag_docs")
    

#     print(f"lightrag_doc_id: {record.lightrag_doc_id}")
#     # LightRagDocStatus es la tabla lightrag_doc_status de lightrag
#     lightrag_record = session2.query(Lmodels.LightRagDocStatus).filter_by(id=record.lightrag_doc_id).first()
#     print(f"lightrag_record id: {lightrag_record.id}")
    
#     doc_ids = [record.lightrag_doc_id]
    
    

#     payload = {
#         "doc_ids":doc_ids,
#         "delete_file":True,
#         "delete_llm_cache":False
#     }
#     # with httpx.Client() as client:
#     #     response = client.post(
#     #         f"{LIGHTRAG_URL}/documents/delete",
#     #         json=payload,
#     #         headers=HEADERS,
#     #         timeout=120
#     #     )

#     with httpx.Client() as client:
#         response = client.delete(
#             f"{LIGHTRAG_URL}/documents/delete_document",
#             json=payload,
#             headers=HEADERS,
#             timeout=120
#         )
#         if not response.is_success:
#             logger.warning(
#                 "LightRAG delete request failed for summary_id=%s: status=%s body=%s",
#                 summary_id, response.status_code, response.text
#             )
#             return None

#         response.raise_for_status()
#         data = response.json()
#         print(f"Documento borrado exitosamente de lightrag: status={data['status']}, message={data['message']}, doc_id={data['doc_id']}")
#         # TODO: Ahora tenemos 
#         session.delete(record)
#         session.commit() 







def insert_to_light_rag(session: Session, summary_id: int):                                                                                                                           
      summary_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=summary_id).first()                                                                        
      channel_record = session.query(models.DiscordChannel).filter_by(id=summary_record.channel_id).first()  

      if (summary_record is None) or (channel_record is None):
          raise ValueError("No se encontraron registros en DiscordChannelChronologicalSummary o DiscordChannel")
                                                                     
                                                                                                                                                                                        
      channel_name = channel_record.name                                                                                                                                                
      start_time = summary_record.start_time.strftime("%d/%m/%Y %H:%M")
      end_time = summary_record.end_time.strftime("%d/%m/%Y %H:%M")                                                                                                                     
                  
      doc_name = f"{channel_name}_from_{start_time}_to_{end_time}"                                                                                                                      
      doc = summary_record.summary
                                                                                                                                                                                        
      payload = { 
          "text": doc,
          "file_source": doc_name,
      }

      with httpx.Client() as client:                                                                                                                                                    
          response = client.post(
              f"{LIGHTRAG_URL}/documents/text",                                                                                                                                         
              json=payload,
              headers=HEADERS,
              timeout=120,                                                                                                                                                              
          )
          if not response.is_success:                                                                                                                                                   
              logger.warning(
                  "LightRAG insert request failed for summary_id=%s: status=%s body=%s",                                                                                                
                  summary_id, response.status_code, response.text,                                                                                                                      
              )                                                                                                                                                                         
              return None                                                                                                                                                               
                  
          data = response.json()
          status = data.get("status")
                                                                                                                                                                                        
          if status == "duplicated":
              logger.warning(                                                                                                                                                           
                  "LightRAG document already exists for summary_id=%s: %s",
                  summary_id, data.get("message"),                                                                                                                                      
              )
              return None                                                                                                                                                               
                  
          track_id = data.get("track_id")
          print(f"Documento insertado exitosamente en LightRAG: track_id={track_id}")

          lightrag_doc_status_record = session.query(Lmodels.LightRagDocStatus).filter(
              Lmodels.LightRagDocStatus.track_id == track_id
          ).first()

          if lightrag_doc_status_record is None:
              raise ValueError("lightrag_doc_status_record es None")

          lightrag_doc_id = lightrag_doc_status_record.id
                                                                                                                                                                                        
          lightrag_doc = models.LightRagDocs(                                                                                                                                           
              summary_id=summary_id,                                                                                                                                                    
              lightrag_doc_id=lightrag_doc_id,                                                                                                                                                 
          )       
          session.add(lightrag_doc)
          session.commit()

          return lightrag_doc_id   







def check_lightrag_status(track_id: str) -> dict:
      with httpx.Client() as client:                                                                                                                                                    
          response = client.get(                                                                                                                                                        
              f"{LIGHTRAG_URL}/documents/status/{track_id}",
              headers=HEADERS,                                                                                                                                                          
              timeout=30                                                                                                                                                                
          )
          response.raise_for_status()                                                                                                                                                   
          return response.json()
          # status puede ser: "pending" | "processing" | "processed" | "failed"



if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src import settings
    import asyncio
    

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()

    delete_in_lightrag_status(session=session, summary_id=315)


"""
python3 -m src.services.v2.LightRagCrud.crud


"""
    

    



# import hashlib                                                                                                                                                                        
# import html                                                                                                                                                                           
# import re                                                                                                                                                                             
                                                                                                                                                                            
# # Replicar exactamente la lógica de LightRAG                                                                                                                                          
# _SURROGATE_PATTERN = re.compile(r"[\ud800-\udfff]")
# _CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")   



                                                                                                                                                                            
# def _compute_lightrag_doc_id(text: str) -> str:                                                                                                                                       
#     """Replica compute_mdhash_id(sanitize_text_for_encoding(text.strip()), prefix='doc-')"""                                                                                          
#     text = text.strip()                                                                                                                                                               
#     text = html.unescape(text)
#     text = _SURROGATE_PATTERN.sub("", text)                                                                                                                                           
#     text = _CONTROL_CHAR_PATTERN.sub("", text)                                                                                                                                        
#     text = text.strip()
#     return "doc-" + hashlib.md5(text.encode("utf-8")).hexdigest()  



# def insert_to_light_rag(session: Session, summary_id: int):                                                                                                                           
#     summary_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=summary_id).first()
#     channel_record = session.query(models.DiscordChannel).filter_by(id=summary_record.channel_id).first()
                                                                                                                                                                                    
#     channel_name = channel_record.name
#     start_time = summary_record.start_time.strftime("%d/%m/%Y %H:%M")                                                                                                                 
#     end_time = summary_record.end_time.strftime("%d/%m/%Y %H:%M")                                                                                                                     

#     doc_name = f"{channel_name}_from_{start_time}_to_{end_time}"                                                                                                                      
#     doc = summary_record.summary
                                                                                                                                                                                    
#     doc_id = _compute_lightrag_doc_id(doc)                                                                                                                                            

#     payload = {                                                                                                                                                                       
#         "text": doc,
#         "file_source": doc_name,
#     }

#     with httpx.Client() as client:                                                                                                                                                    
#         response = client.post(
#             f"{LIGHTRAG_URL}/documents/text",                                                                                                                                         
#             json=payload,
#             headers=HEADERS,
#             timeout=120,                                                                                                                                                              
#         )
#         if not response.is_success:                                                                                                                                                   
#             logger.warning(
#                 "LightRAG insert request failed for summary_id=%s: status=%s body=%s",                                                                                                
#                 summary_id, response.status_code, response.text,                                                                                                                      
#             )                                                                                                                                                                         
#             return None                                                                                                                                                               
                                                                                                                                                                                    
#         data = response.json()
#         status = data.get("status")                                                                                                                                                   
                
#         if status == "duplicated":
#             logger.warning(
#                 "LightRAG document already exists for summary_id=%s: %s",                                                                                                             
#                 summary_id, data.get("message"),
#             )                                                                                                                                                                         
#             return None
                                                                                                                                                                                    
#         logger.info("Documento insertado en LightRAG: doc_id=%s", doc_id)                                                                                                             

#         lightrag_doc = models.LightRagDocs(                                                                                                                                           
#             summary_id=summary_id,
#             lightrag_doc_id=doc_id,
#         )                                                                                                                                                                             
#         session.add(lightrag_doc)
#         session.commit()                                                                                                                                                              
                
#         return doc_id







