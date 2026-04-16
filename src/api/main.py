from fastapi import FastAPI
from src.api.v1.routers import fetchDiscordApi, chunkMessages, summaryApi

app = FastAPI(title="Discord-Echo_Saver", lifespan=fetchDiscordApi.lifespan)
app.include_router(fetchDiscordApi.router)
app.include_router(chunkMessages.router)
app.include_router(summaryApi.router)




"""
uvicorn src.api.main:app --reload


"""
