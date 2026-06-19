"""wiki-attractor -- run amplifier-bundle-llm-wiki workflows as attractor pipelines."""

__version__ = "0.1.0"

from .api import ingest, init, lint, publish, query, review

__all__ = [
    "ingest",
    "init",
    "lint",
    "publish",
    "query",
    "review",
]
