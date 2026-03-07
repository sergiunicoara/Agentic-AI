from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Postgres
    database_url: str = "postgresql+asyncpg://obs:obs@localhost:5432/observability"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # gRPC
    grpc_port: int = 50051

    # REST
    rest_port: int = 8000

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # OTel
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agent-observability-backend"

    # Seed admin
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "password"


settings = Settings()
