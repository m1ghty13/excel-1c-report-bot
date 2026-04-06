"""Central configuration — single Settings object imported everywhere."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration read from environment / .env file."""

    BOT_TOKEN: str
    # Stored as comma-separated strings; use .admin_ids / .allowed_users properties
    ADMIN_IDS: str
    ALLOWED_USERS: str

    REPORT_TIME: str = "09:00"
    TIMEZONE: str = "Europe/Moscow"
    MAX_FILE_SIZE_MB: int = 10
    LOG_LEVEL: str = "INFO"
    DATABASE_PATH: str = "data/reports.db"
    HEALTH_PORT: int = 8080

    UPLOADS_DIR: str = "uploads"
    LOGS_DIR: str = "logs"
    FILE_RETENTION_DAYS: int = 30
    CLEANUP_HOUR_UTC: int = 3
    MAX_HISTORY_ITEMS: int = 10
    LOW_STOCK_THRESHOLD: int = 5
    TOP_PRODUCTS_COUNT: int = 5
    TOP_CATEGORIES_COUNT: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_ids(self) -> list[int]:
        """Parse ADMIN_IDS comma-separated string into list of ints."""
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    @property
    def allowed_users(self) -> list[int]:
        """Parse ALLOWED_USERS comma-separated string into list of ints."""
        return [int(x.strip()) for x in self.ALLOWED_USERS.split(",") if x.strip()]


settings = Settings()
