# file: src/parsers/redis_client.py
import os, urllib.parse, redis

def redis_from_env(db_default: int = 0) -> "redis.Redis":
    url = os.getenv("CELERY_BROKER_URL", "")
    if url.startswith("redis://"):
        pr = urllib.parse.urlparse(url)
        host = pr.hostname or os.getenv("REDIS_HOST", "redis")
        port = pr.port or int(os.getenv("REDIS_PORT", "6379"))
        pwd  = (pr.password or os.getenv("REDIS_PASSWORD", "")) or None
        db   = int(pr.path.lstrip("/") or db_default)
        return redis.Redis(host=host, port=port, password=pwd, db=db, decode_responses=True)
    # fallback: конструируем из REDIS_* переменных
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))
    pwd  = os.getenv("REDIS_PASSWORD") or None
    return redis.Redis(host=host, port=port, password=pwd, db=db_default, decode_responses=True)
