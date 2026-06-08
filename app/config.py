"""
LogSentinel configuration management.

All settings are loaded from environment variables / .env file
using pydantic-settings. No hardcoded values.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Application ---
    app_name: str = Field(default="LogSentinel", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://LogSentinel:LogSentinel@localhost:5432/LogSentinel",
        alias="DATABASE_URL",
    )

    # --- Anomaly Detection ---
    anomaly_error_rate_threshold: float = Field(default=0.15, alias="ANOMALY_ERROR_RATE_THRESHOLD")
    anomaly_latency_threshold_ms: float = Field(
        default=2000.0, alias="ANOMALY_LATENCY_THRESHOLD_MS"
    )
    anomaly_window_size: int = Field(default=100, alias="ANOMALY_WINDOW_SIZE")
    anomaly_window_time_seconds: int = Field(default=300, alias="ANOMALY_WINDOW_TIME_SECONDS")
    anomaly_cooldown_seconds: int = Field(default=60, alias="ANOMALY_COOLDOWN_SECONDS")

    # --- Remediation ---
    remediation_enabled: bool = Field(default=False, alias="REMEDIATION_ENABLED")
    remediation_mode: str = Field(default="mock", alias="REMEDIATION_MODE")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_lambda_function_name: str = Field(
        default="LogSentinel-remediation", alias="AWS_LAMBDA_FUNCTION_NAME"
    )
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")
    remediation_webhook_url: str = Field(default="", alias="REMEDIATION_WEBHOOK_URL")

    # --- Prometheus ---
    prometheus_enabled: bool = Field(default=True, alias="PROMETHEUS_ENABLED")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }


# Singleton settings instance
settings = Settings()
