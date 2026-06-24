"""wiki-attractor -- run amplifier-bundle-llm-wiki workflows as attractor pipelines."""

__version__ = "0.3.0"

from .api import (
    apply_resolutions,
    full_pass,
    ingest,
    ingest_folder,
    init,
    lint,
    publish,
    query,
    query_save,
    review,
)

__all__ = [
    "apply_resolutions",
    "full_pass",
    "ingest",
    "ingest_folder",
    "init",
    "lint",
    "publish",
    "query",
    "query_save",
    "review",
]
