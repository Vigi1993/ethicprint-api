from supabase import Client, create_client
from app.core.config import settings

settings.validate()

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
