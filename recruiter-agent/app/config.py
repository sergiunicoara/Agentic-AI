from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    environment: str = "local"
    service_name: str = "recruiter-agent"
    log_level: str = "INFO"

    # ✔ Use GOOGLE_API_KEY, NOT OPENAI_API_KEY
    GOOGLE_API_KEY: str

    host: str = "0.0.0.0"
    port: int = 9191

def get_settings() -> Settings:
    return Settings()
