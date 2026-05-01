"""Centralized configuration — single source of truth for all settings.

All environment variables are loaded and typed here. No other module
reads os.getenv() directly. Import from this module instead.

Usage:
    from config import settings
    model = settings.model_low
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env relative to repo root (two levels up from code/)
_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")


@dataclass(frozen=True)
class ModelConfig:
    low: str
    medium: str
    high: str


@dataclass(frozen=True)
class RetrievalConfig:
    bm25_top_k: int
    semantic_top_k: int
    final_top_k: int
    embedding_model: str


@dataclass(frozen=True)
class PipelineConfig:
    max_responder_calls: int
    critic_pass_threshold: int


@dataclass(frozen=True)
class PathConfig:
    repo_root: Path
    data_dir: Path
    index_dir: Path
    prompts_dir: Path
    input_csv: Path
    output_csv: Path
    sample_csv: Path


@dataclass(frozen=True)
class Settings:
    """Immutable settings object — frozen after construction."""
    api_key: str
    models: ModelConfig
    retrieval: RetrievalConfig
    pipeline: PipelineConfig
    paths: PathConfig


def _load_settings() -> Settings:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    repo_root = _REPO_ROOT
    code_dir = Path(__file__).resolve().parent
    index_dir = code_dir / "index" / "data"

    return Settings(
        api_key=api_key,
        models=ModelConfig(
            low=os.getenv("MODEL_LOW", "models/gemini-3.1-flash-lite-preview"),
            medium=os.getenv("MODEL_MEDIUM", "models/gemini-3-flash-preview"),
            high=os.getenv("MODEL_HIGH", "models/gemini-3.1-pro-preview"),
        ),
        retrieval=RetrievalConfig(
            bm25_top_k=int(os.getenv("BM25_TOP_K", "20")),
            semantic_top_k=int(os.getenv("SEMANTIC_TOP_K", "5")),
            final_top_k=int(os.getenv("FINAL_TOP_K", "3")),
            embedding_model=os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001"),
        ),
        pipeline=PipelineConfig(
            max_responder_calls=int(os.getenv("MAX_RESPONDER_CALLS", "3")),
            critic_pass_threshold=int(os.getenv("CRITIC_PASS_THRESHOLD", "7")),
        ),
        paths=PathConfig(
            repo_root=repo_root,
            data_dir=repo_root / "data",
            index_dir=index_dir,
            prompts_dir=code_dir / "prompts",
            input_csv=repo_root / "support_tickets" / "support_tickets.csv",
            output_csv=repo_root / "support_tickets" / "output.csv",
            sample_csv=repo_root / "support_tickets" / "sample_support_tickets.csv",
        ),
    )


# Module-level singleton — import this everywhere
settings: Settings = _load_settings()
