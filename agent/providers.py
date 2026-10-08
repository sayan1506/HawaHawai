"""Explicit Strands providers; never fall through to a default paid Bedrock model."""
import os


class ProviderNotConfigured(ValueError):
    pass


def create_model(provider: str):
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise ProviderNotConfigured("GEMINI_API_KEY is empty")
        from strands.models.gemini import GeminiModel
        return GeminiModel(
            client_args={"api_key": key, "http_options": {"timeout": 20000}},
            model_id=os.environ.get("HAWAHAWAI_GEMINI_MODEL", "gemini-2.5-flash"),
            params={"temperature": 0, "max_output_tokens": 256},
        )
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise ProviderNotConfigured("GROQ_API_KEY is empty")
        from strands.models.openai import OpenAIModel
        return OpenAIModel(
            client_args={"api_key": key, "base_url": "https://api.groq.com/openai/v1", "timeout": 20, "max_retries": 0},
            model_id=os.environ.get("HAWAHAWAI_GROQ_MODEL", "llama-3.3-70b-versatile"),
            params={"temperature": 0, "max_tokens": 256},
        )
    if provider == "bedrock":
        raise ProviderNotConfigured("Bedrock is disabled for Phase 0; explicit access/cost review is required")
    raise ProviderNotConfigured("Unsupported AI provider")
