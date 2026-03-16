import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    APP_NAME = "EthicPrint API"
    APP_VERSION = "2.0.0"

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    APP_CORS_ORIGINS = os.getenv("APP_CORS_ORIGINS", "*")

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not cls.SUPABASE_KEY:
            missing.append("SUPABASE_KEY")
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


settings = Settings()
