from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app config. Values are loaded from environment variables / .env file.
    Never hardcode secrets here — this file only defines *names* and defaults.
    """

    database_url: str
    firebase_credentials_path: str
    env: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Singleton settings instance — import this everywhere instead of re-reading env vars.
settings = Settings()
