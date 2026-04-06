from .prompt import BUILD_ENTYTI_RELATIONPSHIPS_PROMPT_1
from langchain_core.language_models.chat_models import BaseChatModel
from neo4j import GraphDatabase

from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel
from typing import TypedDict ,List


DISCORD_OBJECK_NODE_TEMPLATE = """
MERGE (e:DiscordObjeck {{id : $discord_id }})  // Este es unico creo que no se necesita MERGE
SET e.description = $description
SET e.name = $name
SET e.discord_id = $discord_id
"""

CHUNK_NODE_TEMPLATE = """
MERGE (e:Chunk {{chunk_id : $chunk_id}}) // Este es unico creo que no se necesita MERGE
SET e.start = $start
SET e.end = $end
SETe.summary = $summary
"""

CHUNK_RELATIONPHIP_TEMPLATE = """
MATCH (s {{chunk_id : $chunk_id_source}})
MATCH (t {{chunk_id : $chunk_id_target}})
MERGE (s)-[NEXT]->(t)
"""

ENTITY_NODE_TEMPLATE = """
MERGE (e:Entity {{entity_name :$entity_name}})
SET e.descriptions = $descriptions  // Aqui me gustaria que cada vez que se hacer merge de el nombre de una entidad ya existente e.description sea una lista que guarde cada descripcion y no la sobre escriba
"""


ENTYTI_RELATIONSHIP_TEMPLATE = """
MATCH (a {{entyti_name : $entyti_name_source}})
MATCH (b {{entyti_name : $entyti_name_target}})
MERGE (a)-[r : $rel_type]-> (b)
SET r.descriptions = $descriptions // Aqui tambien me gustaria que se guardara en una lista
"""


class Entyti(TypedDict):
    entity_name : str
    entity_description : str


class RelationShip(TypedDict):
    source_entity : str
    target_entity : str
    relationship_type : str
    relationship_description : str

class EntitiesRelationships(TypedDict):
    entities : List[Entyti]
    relationships : List[RelationShip]

class LLmResponse(BaseModel):
    content : EntitiesRelationships

