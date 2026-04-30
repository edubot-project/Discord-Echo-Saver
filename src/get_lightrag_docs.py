from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import settings
from src import discord_models
from src import lighrag_models as lr_models
import re


engine_lihgt_rag = create_engine(settings.LIGHTRAG_CONN_STRING)

engine_discord = create_engine(settings.APP_CONN_STRING)


LightragSession = sessionmaker(bind=engine_lihgt_rag)
lihgtrag_session = LightragSession()

DiscordSession = sessionmaker(bind=engine_discord)
discord_session = DiscordSession()


lightrag_doc_dict = {}
def safe_name(name: str) -> str:
    return re.sub(r"[^\w\-_. ]", "_", name)

def extract_channel_summary(path: str) -> str:
    parts = path.split('/')
    for i, part in enumerate(parts):
        if part.startswith('channel_'):
            return '/'.join(parts[i:])
    return path


channel_records = discord_session.query(discord_models.DiscordChannel).filter(
    discord_models.DiscordChannel.last_messages_at.is_not(None)
).all()

for channel in channel_records:
    name = safe_name(channel.name)
    idx = channel.id
    n = 1
    summary_records = discord_session.query(discord_models.DiscordChannelChronologicalSummary).filter_by(channel_id=idx).order_by(discord_models.DiscordChannelChronologicalSummary.start_time).all()
    for summary in summary_records:
        key = f"channel_{name}/Summary_{n}" 
        lightrag_doc_dict[key] = summary.id
        n += 1
    
    

docs_records = lihgtrag_session.query(lr_models.LightRagDocFull).all()

N = 1
for doc in docs_records:
    print(f"procesando doc {N}")
    doc_name = doc.doc_name
    key = extract_channel_summary(doc_name)
    summ_id = lightrag_doc_dict[key]
    
    record = discord_models.LightRagDocs(
        lightrag_doc_id=doc.id,
        summary_id=summ_id
    )
    discord_session.add(record)

discord_session.commit()



"""
python3 -m src.get_lightrag_docs


"""