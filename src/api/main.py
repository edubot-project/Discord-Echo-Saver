from fastapi import FastAPI
from src.api.v1.routers import fetchDiscordApi

app = FastAPI(title="Discord-Echo_Saver", lifespan=fetchDiscordApi.lifespan)
app.include_router(fetchDiscordApi.router)




"""
uvicorn src.api.main:app --reload


"""
