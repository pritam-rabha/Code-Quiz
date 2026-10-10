"""Gunicorn configuration (Render compatible)."""
import os

# Render provides PORT; bind to all interfaces.
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"

# JSON storage is guarded by an in-process lock plus a cross-process file lock,
# but a single worker with several threads is the simplest safe setup.
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
