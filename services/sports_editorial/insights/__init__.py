"""Structured Alpine skiing insight engine used by the compatibility facade."""

from .engine import build_engine_result
from .models import Insight

__all__ = ["Insight", "build_engine_result"]
