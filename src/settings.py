from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

APP_CONN_STRING = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") # token con permisos maximos
DULCINEA_DISCORD_BOT_TOKEN = os.getenv("DULCINEA_DISCORD_BOT_TOKEN")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")






if __name__=="__main__":
    print(ROOT)



"""
python3 -m src.settings


"""