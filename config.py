from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — app fails to boot if any is missing (validated on instantiation).
    mysql_url: str
    jwt_secret: str
    aws_s3_bucket_name: str
    aws_access_key_id: str
    aws_secret_access_key: str

    # Optional
    aws_endpoint_url: str | None = None
    aws_default_region: str | None = None
    allowed_origins: str = "*"  # comma-separated
    access_ttl_hours: int = 12
    refresh_ttl_days: int = 30
    sentry_dsn: str | None = None

    # Email (optional). Without SMTP configured, links are logged instead of sent.
    app_base_url: str = "http://localhost:8000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
