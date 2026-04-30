
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




def delete_in_lightrag_status(session: Session, summary_id: int):                                                                                                                     
    """         
    Solicita a LightRAG que borre el documento y marca el registro
    como pending_deletion=True. El borrado real en LightRagDocs                                                                                                                       
    ocurre cuando sweep_pending_deletions confirme que LightRAG terminó.
    """                                                                                                                                                                               
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
        response = client.request(
            "DELETE",
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
        logger.info(f"data: \n {data} \n\n") 
        status = data.get("status")
                                                                                                                                                                                        
    if status == "busy":
        logger.warning(                                                                                                                                                                   
            "LightRAG ocupado, borrado no iniciado para summary_id=%s", summary_id
        )
        return None  # NO marcar pending_deletion
                                                                                                                                                                                        
    if status != "deletion_started":
        logger.warning(                                                                                                                                                                   
            "Estado inesperado de LightRAG para summary_id=%s: %s", summary_id, status
        )                                                                                                                                                                                 
        return None
                                                                                                                                                                                        
    logger.info("Borrado iniciado en LightRAG para doc_id=%s: %s", doc_id, data)

                                                                                                                                                                                    
    record.pending_deletion = True
    session.commit()                                                                                                                                                                  
    logger.info("summary_id=%s marcado como pending_deletion", summary_id)







def sweep_pending_deletions(session: Session):
    """
    Recorre todos los registros con pending_deletion=True y verifica en la DB                                                                                                         
    de LightRagDocs. Pensado para ejecutarse periódicamente.                  
    """                                                                                                                                                                               
    pending = session.query(models.LightRagDocs).filter_by(pending_deletion=True).all()
                                                                                                                                                                                    
    if not pending:                                                                                                                                                                   
        logger.info("sweep_pending_deletions: sin registros pendientes")
        return                                                                                                                                                                        
                
    logger.info("sweep_pending_deletions: revisando %d registros", len(pending))
                                                                                                                                                                                    
    deleted_count = 0
    still_pending_count = 0                                                                                                                                                           
                            
    for record in pending:
        session2.expire_all()  # evita caché de SQLAlchemy
        lightrag_record = session2.query(Lmodels.LightRagDocStatus).filter_by(
            id=record.lightrag_doc_id                                                                                                                                                 
        ).first()                                                                                                                                                                     
                                                                                                                                                                                    
        if lightrag_record is None:                                                                                                                                                   
            session.delete(record) 
            deleted_count += 1    
            logger.info(      
                "Eliminado de lightrag_docs: doc_id=%s summary_id=%s",
                record.lightrag_doc_id, record.summary_id,            
            )
            summary_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=record.summary_id).first()      
            summary_record.status = None
            session.add(summary_record)                                                                                                                                                          
        else:
            still_pending_count += 1                                                                                                                                                  
            logger.info(            
                "Aún pendiente en LightRAG: doc_id=%s",
                record.lightrag_doc_id,                                                                                                                                               
            )                          
                                                                                                                                                                                    
    session.commit()
    logger.info(    
        "sweep completado: %d eliminados, %d aún pendientes",
        deleted_count, still_pending_count,                  
    )  







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






if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src import settings
    import asyncio
    

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()

    # delete_in_lightrag_status(session=session, summary_id=315)
    sweep_pending_deletions(session=session)



"""
python3 -m src.services.v2.LightRagCrud.crud2


"""