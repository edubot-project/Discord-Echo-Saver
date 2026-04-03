import discord
from typing import List
from src import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from src import models
from typing import Union
import time



class DiscordEchoSaverBot(discord.Client):
    def __init__(self, *, intents : discord.Intents, root_id : int):  
        super().__init__(intents=intents)
        self.engine = create_engine(settings.APP_CONN_STRING)
        self.root_id = root_id
        

 