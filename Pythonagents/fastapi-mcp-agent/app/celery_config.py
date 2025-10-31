import os
from celery import Celery
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    'llm_middleware',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2'),
    include=['app.tasks.llm_tasks']
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time
    task_acks_late=True,  # Acknowledge tasks after completion
    worker_disable_rate_limits=False,

    # Queue settings
    task_default_queue='llm_requests',
    task_queues={
        'llm_requests': {
            'exchange': 'llm_requests',
            'routing_key': 'llm_requests',
        },
        'high_priority': {
            'exchange': 'llm_requests',
            'routing_key': 'high_priority',
        },
        'batch_requests': {
            'exchange': 'llm_requests',
            'routing_key': 'batch_requests',
        }
    },

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_cache_max=10000,

    # Rate limiting
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
)