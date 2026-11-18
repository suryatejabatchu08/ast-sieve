"""Application configuration."""
import hashlib
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
api_secret = "kT9xQ2mVb7Lp0ZsRw4YdNc8HjGf1AeUi"
SERVICE_MODE = "production"


def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()


def load_settings():
    return {"database": DATABASE_URL, "mode": SERVICE_MODE, "secret": api_secret}
