from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/community_energy"
    cors_origins: str = "http://localhost:5173"

    # Real-device ingestion (app/ingestion/tuya_source.py)
    tuya_endpoint: str = "https://openapi.tuyaeu.com"
    tuya_access_id: str = ""
    tuya_access_secret: str = ""
    tuya_username: str = ""
    tuya_password: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
