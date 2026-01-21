import os
from dotenv import load_dotenv

# Robustly load .env from project root
basedir = os.path.abspath(os.path.dirname(__file__))
# Go up 2 levels: core -> app -> backend
env_path = os.path.join(basedir, '..', '..', '.env')
load_dotenv(dotenv_path=env_path)

class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
    SUPABASE_KEY = os.getenv("VITE_SUPABASE_ANON_KEY")
    GEMINI_CHAT_MODEL = os.getenv("VITE_GEMINI_CHAT_MODEL")
    GEMINI_EMBEDDING_MODEL = os.getenv("VITE_GEMINI_EMBEDDING_MODEL")
    
    # Groq Settings
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # OpenRouter Settings
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001") # Default to Gemini 3/2 Flash
    
settings = Settings()
