"""
LLM Adapters Package
Provides adapter pattern for swappable LLM providers.
"""

from .config import get_adapter, ACTIVE_PROVIDER, list_providers, get_provider_info
from .base_adapter import BaseLLMAdapter

__all__ = ['get_adapter', 'BaseLLMAdapter', 'ACTIVE_PROVIDER', 'list_providers', 'get_provider_info']

