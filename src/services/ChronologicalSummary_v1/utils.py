
from sqlalchemy.orm import Session
from src import models



def configurar_number_messages(session : Session, idx : int, cantidad : int):
    db_record = session.query(models.DiscordChannelChronologicalSummary).filter_by(id=idx).first()
    db_record.number_messages = cantidad
    session.add(db_record)
    session.close()


