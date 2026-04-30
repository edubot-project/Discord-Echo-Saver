
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


from typing import List, TypedDict, Dict
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import settings
import asyncio


engine = create_engine(settings.LIGHTRAG_CONN_STRING)
MySession2 = sessionmaker(bind=engine)
session2 = MySession2()




def delete_in_lightrag_status(session: Session, summary_ids: List[int]):                                                                                                                     
    """         
    Solicita a LightRAG que borre el documento y marca el registro
    como pending_deletion=True. El borrado real en LightRagDocs                                                                                                                       
    ocurre cuando sweep_pending_deletions confirme que LightRAG terminó.
    """ 

    summary_ids_set = set(summary_ids)                                                                                                                                                                              
    records = session.query(models.LightRagDocs).filter(
        models.LightRagDocs.summary_id.in_(summary_ids_set)
    ).all()

    if records is None:                                                                                                                                                                
        logger.info(f"No hay registros en LightRagDocs que su status sea in_lightrag y su summary sea vacio")
        return None
                                                                                                                                                                                    
    doc_ids = [obj.lightrag_doc_id for obj in records]

    payload = {                                                                                                                                                                       
        "doc_ids": doc_ids,
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
                "LightRAG delete request failed",                                                                                                                     
            )
            return None    
                                                                                                                                                                   
               
        data = response.json()
        #logger.info(f"data: \n {data} \n\n") 
        #status = data.get("status")
                                                                                                                                                                                        
                                                                                                                                                                                        
    logger.info(f"Borrado iniciado en LightRAG. Data: \n\n {data} \n\n")

                                                                                                                                                                                    
    for r in records:
        r.pending_deletion = True
        session.add(r)
    session.commit()







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
            summary_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=record.summary_id).first()      
            summary_record.status = None
            session.add(summary_record)   

            session.delete(record) 
            deleted_count += 1    
            logger.info(      
                "Eliminado de lightrag_docs: doc_id=%s summary_id=%s",
                record.lightrag_doc_id, record.summary_id,            
            )                                                                                                                                                         
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






def insert_to_light_rag(session: Session, summary_id: int, channel_id : int, start_time : datetime, end_time : datetime, summary : str):                                                            
    channel_record = session.query(models.DiscordChannel).filter_by(id=channel_id).first()  
    
    if (channel_record is None):
        raise ValueError("No se encontraron registros en DiscordChannelChronologicalSummary o DiscordChannel")
    
    logger.info(f"incertando documento con summary_id: {summary_id} del canal {channel_record.name}")
                                                                
                                                                                                                                                                                
    channel_name = channel_record.name                                                                                                                                                
    start_time = start_time.strftime("%d/%m/%Y %H:%M")
    end_time = end_time.strftime("%d/%m/%Y %H:%M")                                                                                                                     
            
    doc_name = f"{channel_name}_from_{start_time}_to_{end_time}"                                                                                                                      
    doc = summary
                                                                                                                                                                                
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
    logger.info(f"data: \n\n {data} \n\n")
                                                                                                                                                                                
    if status == "duplicated":
        logger.warning(                                                                                                                                                           
            "LightRAG document already exists for summary_id=%s: %s",
            summary_id, data.get("message"),                                                                                                                                      
        )
        return None                                                                                                                                                               
            
    track_id = data.get("track_id")
    print(f"Documento insertado exitosamente en LightRAG: track_id={track_id}")


    # session.expire_all()
    # lightrag_doc_status_record = session.query(Lmodels.LightRagDocStatus).filter(
    #     Lmodels.LightRagDocStatus.track_id == track_id
    # ).first()

    # if lightrag_doc_status_record is None:
    #     raise ValueError("lightrag_doc_status_record es None")

    # lightrag_doc_id = lightrag_doc_status_record.id
                                                                                                                                                                                
    lightrag_doc = models.LightRagDocs(                                                                                                                                           
        summary_id=summary_id,                                                                                                                                                    
        lightrag_doc_id=None,
        lightrag_track_id=track_id                                                                                                                                               
    )

    session.add(lightrag_doc)
    session.commit()



class PendingTracks(TypedDict):
    lightrag_track_ids : List[str]
    lightrag_track_ids_dict : Dict[str , int]


def sync_processed_lightrag_docs(session: Session, pendingtracks: PendingTracks) -> int:                                                                                                      
    """                                                                                                                                                                               
    Recibe una lista de track_ids, busca en lightrag_doc_status los que ya                                                                                                            
    tienen status 'processed', y actualiza lightrag_doc_id en LightRagDocs.                                                                                                           
    Retorna el número de registros actualizados.                                                                                                                                      
    """

    track_ids = pendingtracks.get("lightrag_track_ids")
    if not track_ids:                                                                                                                                                                 
        return 0

    session2.expire_all()                                                                                                                                                             
    processed = (
        session2.query(Lmodels.LightRagDocStatus)                                                                                                                                     
        .filter(
            Lmodels.LightRagDocStatus.track_id.in_(track_ids),
            Lmodels.LightRagDocStatus.status == "processed",                                                                                                                          
        )
        .all()                                                                                                                                                                        
    )           

    if not processed:
        logger.info("Ningún track_id ha sido procesado aún.")
        return 0                                                                                                                                                                      

    track_to_doc_id = {r.track_id: r.id for r in processed}   
    lightrag_track_ids_dict = pendingtracks.get("lightrag_track_ids_dict")                                                                                                                        
                
    updated = 0                                                                                                                                                                       
    for track_id, doc_id in track_to_doc_id.items():
        count = (
            session.query(models.LightRagDocs)                                                                                                                                        
            .filter(
                models.LightRagDocs.lightrag_track_id == track_id,                                                                                                                    
                models.LightRagDocs.lightrag_doc_id.is_(None),
            )                                                                                                                                                                         
            .update({"lightrag_doc_id": doc_id})
        )                                                                                                                                                                             
        updated += count

        summary_id = lightrag_track_ids_dict[track_id]
        record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=summary_id).first()
        record.status = "in_lightrag"
        session.add(record)


    session.commit()
    logger.info(f"sync_processed_lightrag_docs: {updated} docs actualizados.")


    return updated 






def get_pending_track_ids(session: Session) -> PendingTracks:
    records = session.query(models.LightRagDocs).filter(
        models.LightRagDocs.lightrag_doc_id.is_(None)
    ).all()
    
    lightrag_track_ids = []
    lightrag_track_ids_dict = dict([])
    for r in records:
        x = r.lightrag_track_id
        if x in None:
            raise ValueError("x es None")
        y = r.summary_id
        lightrag_track_ids.append(x)
        lightrag_track_ids_dict[x] = y
        
        
    return {"lightrag_track_ids":lightrag_track_ids, "lightrag_track_ids_dict":lightrag_track_ids_dict}





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


