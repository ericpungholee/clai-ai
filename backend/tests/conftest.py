import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://clai@postgres:5432/clai")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
