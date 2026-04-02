from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_TITLE: str = "Screenshot API"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5181"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # MongoDB
    MONGO_URL: str = "mongodb://localhost:27017/"
    MONGO_DB_NAME: str = "pprint"

    # JWT
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"

    # Game Config
    PIXEL_RECOVERY_INTERVAL: int = 60  # segundos
    PERSISTENCE_INTERVAL: int = 10  # segundos
    PIXELS_MAX: int = 60
    RATE_LIMIT_MS: int = 100  # ms between pixels

    # Browser (legacy)
    BROWSER_VIEWPORT_WIDTH: int = 1280
    BROWSER_VIEWPORT_HEIGHT: int = 800
    BROWSER_TIMEOUT: int = 60000

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


settings = Settings()
