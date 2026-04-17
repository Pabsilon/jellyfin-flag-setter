from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    jellyfin_url: str = ""
    jellyfin_api_key: str = ""
    secret_key: str = ""
    db_path: str = "data/flagsetter.db"


settings = Settings()  # type: ignore[missing-argument]
