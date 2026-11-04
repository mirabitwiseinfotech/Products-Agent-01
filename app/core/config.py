from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Shopify
    SHOPIFY_STORE_DOMAIN: str
    SHOPIFY_ADMIN_ACCESS_TOKEN: str
    SHOPIFY_API_VERSION: str = "2026-07"

    # MongoDB
    MONGODB_URI: str
    MONGODB_DATABASE: str = "shopify_agent_platform"

    # Google Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"

    # Agent
    MAX_PRODUCTS_PER_AUDIT: int = 50
    MIN_DESCRIPTION_WORDS: int = 35

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()