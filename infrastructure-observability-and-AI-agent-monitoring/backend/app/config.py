import json

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # Postgres
    database_url: str = "postgresql+asyncpg://obs:obs@localhost:5432/observability"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # gRPC
    grpc_port: int = 50051

    # REST
    rest_port: int = 8000

    # JWT (internal session tokens issued after OIDC auth)
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # OIDC
    oidc_issuer_url: str = "https://accounts.google.com"   # override in .env
    oidc_client_id: str = ""
    oidc_client_secret: str = ""                            # empty = public client
    oidc_redirect_uri: str = "http://localhost:5173/auth/callback"

    # gRPC emit auth — SDK agents must send this in x-api-key metadata
    emit_api_key: str = ""
    # Optional JSON object mapping agent names to dedicated ingestion keys.
    # In production, this must be configured; the single key is development-only.
    emit_agent_keys: str = ""

    # CORS — exact frontend origin (no wildcard with credentials)
    frontend_origin: str = "http://localhost:5173"

    # OTel
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agent-observability-backend"

    @model_validator(mode="after")
    def validate_runtime_security(self):
        if self.environment.lower() in {"production", "prod"}:
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters in production")
            if not self.frontend_origin.startswith("https://"):
                raise ValueError("FRONTEND_ORIGIN must use HTTPS in production")
            if not self.oidc_redirect_uri.startswith("https://"):
                raise ValueError("OIDC_REDIRECT_URI must use HTTPS in production")
            try:
                agent_keys = json.loads(self.emit_agent_keys)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("EMIT_AGENT_KEYS must be a JSON object in production") from exc
            if not isinstance(agent_keys, dict) or not agent_keys or any(len(str(key)) < 32 for key in agent_keys.values()):
                raise ValueError("EMIT_AGENT_KEYS must contain one 32+ character key per agent in production")
        return self


settings = Settings()
