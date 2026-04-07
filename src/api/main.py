from fastapi import FastAPI
from src.api.v1.routers import fetchDiscordApi

app = FastAPI(title="Discord-Echo_Saver")
app.include_router(fetchDiscordApi.router)




"""
uvicorn src.api.main:app --reload


"""
