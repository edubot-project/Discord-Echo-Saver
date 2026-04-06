from .prompt import BUILD_ENTYTI_RELATIONPSHIPS_PROMPT_1
from langchain_core.language_models.chat_models import BaseChatModel
from neo4j import GraphDatabase

from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel
from typing import TypedDict ,List

from sqlalchemy.orm import Session
from src import models

# Usamos coalesce para inicializar una lista vacía si es la primera vez
# y luego sumamos el nuevo elemento dentro de corchetes [$descriptions]
ENTITY_NODE_TEMPLATE = """
MERGE (e:Entity {entity_name: $entity_name})
SET e.descriptions = coalesce(e.descriptions, []) + $descriptions
"""

# Nota: El tipo de relación se inyecta como string porque Cypher no permite 
# parámetros $ para etiquetas de tipo de relación directamente de forma nativa fácil.
ENTYTI_RELATIONSHIP_TEMPLATE = """
MATCH (a {entity_name: $entyti_name_source})
MATCH (b {entity_name: $entyti_name_target})
MERGE (a)-[r:RELATED_TO {type: $rel_type}]->(b)
SET r.descriptions = coalesce(r.descriptions, []) + $descriptions
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

def make_graph_collection(chunk_content: str, llm: BaseChatModel) -> bool:
    URI = "bolt://localhost:7687"
    USER = "neo4j"
    PASSWORD = "dulcinea200"

    driver = GraphDatabase.driver(uri=URI, auth=(USER, PASSWORD))
    parser = JsonOutputParser()

    try:
        prompt = BUILD_ENTYTI_RELATIONPSHIPS_PROMPT_1.format(text=chunk_content)
        ai_message = llm.invoke(prompt)
        llmresponse_raw = parser.parse(ai_message.content)
        llmresponse = LLmResponse(content=llmresponse_raw)

        entities = llmresponse.content.get("entities", [])
        relationships = llmresponse.content.get("relationships", [])

        with driver.session() as neo_session:
            # Procesar Entidades
            for entity in entities:
                neo_session.run(
                    ENTITY_NODE_TEMPLATE,
                    entity_name=entity.get("entity_name"),
                    descriptions=entity.get("entity_description") # Neo4j lo guardará como el siguiente elemento de la lista
                )
            
            # Procesar Relaciones
            for relation in relationships:
                # Aquí usamos una pequeña lógica extra para el tipo de relación
                # ya que Cypher no acepta parámetros para el Label de la relación
                rel_query = f"""
                MATCH (a:Entity {{entity_name: $source}})
                MATCH (b:Entity {{entity_name: $target}})
                MERGE (a)-[r:{relation.get('relationship_type', 'RELATED_TO')}]->(b)
                SET r.descriptions = coalesce(r.descriptions, []) + $desc
                """
                neo_session.run(
                    rel_query,
                    source=relation.get("source_entity"),
                    target=relation.get("target_entity"),
                    desc=relation.get("relationship_description")
                )
        return True

    except Exception as e:
        print(f"\n\nError en el grafo: {e}\n\n")
        return False
    finally:
        driver.close()


def main(session : Session, llm : BaseChatModel):
    records = session.query(models.DiscordChannelChronologicalSummary).filter(
        models.DiscordChannelChronologicalSummary.number_messages >= 15
    )
    for obj in records:
        make_graph_collection(chunk_content=obj.summary, llm=llm)

        


if __name__ == "__main__":
    from langchain_google_genai import ChatGoogleGenerativeAI
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src import settings

    engine = create_engine(settings.APP_CONN_STRING)
    MySession = sessionmaker(bind=engine)
    session = MySession()

    model = "gemini-2.0-flash"
    llm = ChatGoogleGenerativeAI(model=model, temperature=0.5, google_api_key=settings.GOOGLE_API_KEY)

    main(session=session, llm=llm)



"""
python3 -m src.services.KnowledgeGraph_v1.mainv1


"""