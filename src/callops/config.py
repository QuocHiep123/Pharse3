"""Cấu hình đọc từ biến môi trường / file .env (prefix CALLOPS_)."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CALLOPS_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    opensearch_url: str = "http://localhost:9200"
    backend: Literal["auto", "memory"] = "auto"
    log_level: str = "DEBUG"
    log_dir: str = "logs"
    seed: int = 42
