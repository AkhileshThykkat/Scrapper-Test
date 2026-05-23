from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/review_intel"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_reviews_per_company: int = 200
    scrape_delay_min: float = 1.0
    scrape_delay_max: float = 3.0
    max_scroll_attempts: int = 30
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
