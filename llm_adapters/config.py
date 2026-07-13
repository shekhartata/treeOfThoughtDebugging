"""
LLM Adapter Configuration
Controls which LLM provider is used.

To switch providers:
1. Set LLM_PROVIDER environment variable: export LLM_PROVIDER=groq
2. Or change ACTIVE_PROVIDER below
3. Ensure the appropriate API key is set (OPENAI_API_KEY or GROQ_API_KEY)

Available providers:
- "openai": GPT-5 via OpenAI API (default, current implementation)
- "groq": DeepSeek-R1-Distill-Llama-70B via Groq API (fast inference)
"""

import os
import logging

logger = logging.getLogger(__name__)

# Default provider - can be overridden by LLM_PROVIDER environment variable
DEFAULT_PROVIDER = "openai"

# Get active provider from environment or use default
ACTIVE_PROVIDER = os.getenv('LLM_PROVIDER', DEFAULT_PROVIDER).lower()

# Provider-specific model defaults
PROVIDER_MODELS = {
    "openai": "gpt-5",
    "groq": "openai/gpt-oss-120b",
    "ollama": "llama3.1"
}


def get_adapter(provider: str = None, **kwargs):
    """
    Factory function to get the appropriate LLM adapter.
    
    Args:
        provider: Provider name ("openai", "groq", "ollama"). If None, uses ACTIVE_PROVIDER.
        **kwargs: Additional arguments passed to adapter constructor (e.g., api_key, model, base_url)
    
    Returns:
        BaseLLMAdapter instance
    
    Examples:
        # Use default provider (from env or config)
        adapter = get_adapter()
        
        # Explicitly use OpenAI
        adapter = get_adapter("openai")
        
        # Use Groq with custom model
        adapter = get_adapter("groq", model="llama-3.1-70b-versatile")
        
        # Use OpenAI with custom API key
        adapter = get_adapter("openai", api_key="sk-...")
        
        # Use Ollama with default local instance
        adapter = get_adapter("ollama", model="qwen2.5:14b")
        
        # Use Ollama with custom URL (e.g., LM Studio)
        adapter = get_adapter("ollama", base_url="http://localhost:1234/v1", model="llama3.1")
    """
    provider = (provider or ACTIVE_PROVIDER).lower()
    
    if provider == "openai":
        from .openai_adapter import OpenAIAdapter
        logger.info(f"Using OpenAI adapter with model: {kwargs.get('model', PROVIDER_MODELS['openai'])}")
        return OpenAIAdapter(**kwargs)
    
    elif provider == "groq":
        from .groq_adapter import GroqAdapter
        logger.info(f"Using Groq adapter with model: {kwargs.get('model', PROVIDER_MODELS['groq'])}")
        return GroqAdapter(**kwargs)
    
    elif provider == "ollama":
        from .ollama_adapter import OllamaAdapter
        # Extract base_url and model if provided, otherwise use defaults
        base_url = kwargs.pop('base_url', "http://localhost:11434")
        model = kwargs.pop('model', PROVIDER_MODELS['ollama'])
        
        # Ensure base_url ends with /v1 for OpenAI-compatible API
        if not base_url.endswith('/v1'):
            # Remove trailing slash if present, then add /v1
            base_url = base_url.rstrip('/') + '/v1'
        
        logger.info(f"Using Ollama adapter with model: {model}, base_url: {base_url}")
        return OllamaAdapter(base_url=base_url, model=model, **kwargs)
    
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Available providers: {list(PROVIDER_MODELS.keys())}"
        )


def list_providers():
    """List all available LLM providers."""
    return list(PROVIDER_MODELS.keys())


def get_provider_info(provider: str = None) -> dict:
    """Get information about a provider."""
    provider = (provider or ACTIVE_PROVIDER).lower()
    
    if provider not in PROVIDER_MODELS:
        raise ValueError(f"Unknown provider: {provider}")
    
    if provider == "openai":
        env_key = "OPENAI_API_KEY"
    elif provider == "groq":
        env_key = "GROQ_API_KEY"
    else:  # ollama
        env_key = None  # Ollama doesn't require API keys
    
    return {
        "provider": provider,
        "default_model": PROVIDER_MODELS[provider],
        "env_key": env_key,
        "api_key_set": bool(os.getenv(env_key)) if env_key else None,
        "is_active": provider == ACTIVE_PROVIDER,
        "is_local": provider == "ollama"
    }

