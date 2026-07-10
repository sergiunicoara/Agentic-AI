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

    # JWT (internal session tokens issued after OIDC auth)
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # OIDC
    oidc_issuer_url: str = "https://accounts.google.com"   # override in .env
    oidc_client_id: str = ""
    oidc_client_secret: str = ""                            # empty = public client
    oidc_redirect_uri: str = "http://localhost:5173/auth/callback"

    # gRPC emit auth — SDK agents must send this in x-api-key metadata
    emit_api_key: str = "dev-emit-key"

    # CORS — exact frontend origin (no wildcard with credentials)
    frontend_origin: str = "http://localhost:5173"

    # OTel
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agent-observability-backend"


settings = Settings()
