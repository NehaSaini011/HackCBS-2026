from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads backend/.env locally; on DigitalOcean the same names come
    # from the app's encrypted settings instead. Names are not case-sensitive.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    yb_url: str
    mongodb_uri: str
    mongodb_db: str = "fixnet"
    jwt_secret: str
    jwt_hours: int = 12
    allowed_origins: str = "http://localhost:5173"   # comma-separated list

    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-2.5-flash"
    gemini_embed_model: str = "gemini-embedding-001"

    meko_backend: str = "mock"      # "mock" or "mcp"
    meko_mcp_url: str = ""
    meko_api_key: str = ""
    meko_datapack: str = ""


settings = Settings()   # import this object everywhere: from app.settings import settings