from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "review_intel",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_queues={
        "scrape_queue": {"exchange": "default", "routing_key": "scrape"},
        "analysis_queue": {"exchange": "default", "routing_key": "analysis"},
    },
)
