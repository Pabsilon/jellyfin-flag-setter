from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    jellyfin_url: str = ""
    jellyfin_api_key: str = ""
    recent_movies_limit: int = 20


settings = Settings()  # type: ignore[missing-argument]
