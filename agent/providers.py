"""Explicit Strands providers; never fall through to a default paid Bedrock model."""
import os


class ProviderNotConfigured(ValueError):
    pass


def create_model(provider: str, credentials=None, timeout=6):
    credentials = os.environ if credentials is None else credentials
    if provider == "gemini":
        key = credentials.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise ProviderNotConfigured("GEMINI_API_KEY is empty")
        from strands.models.gemini import GeminiModel
        from .explanations import ExplanationPlan
        return GeminiModel(
            # Gemini rejects server deadlines below 10s. asyncio enforces the
            # shorter application deadline and cancels the in-flight request.
            client_args={"api_key": key, "http_options": {"timeout": max(10000, int(timeout * 1000)), "retry_options": {"attempts": 1}}},
            model_id=os.environ.get("HAWAHAWAI_GEMINI_MODEL", "gemini-2.5-flash"),
            params={"temperature": 0, "max_output_tokens": 1024, "thinking_config": {"thinking_budget": 0},
                "response_mime_type": "application/json", "response_json_schema": ExplanationPlan.model_json_schema(),
                "tool_config": {"function_calling_config": {"mode": "NONE"}}},
        )
    if provider == "groq":
        key = credentials.get("GROQ_API_KEY", "").strip()
        if not key:
            raise ProviderNotConfigured("GROQ_API_KEY is empty")
        from strands.models.openai import OpenAIModel
        return OpenAIModel(
            client_args={"api_key": key, "base_url": "https://api.groq.com/openai/v1", "timeout": timeout, "max_retries": 0},
            model_id=os.environ.get("HAWAHAWAI_GROQ_MODEL", "llama-3.3-70b-versatile"),
            params={"temperature": 0, "max_tokens": 1024, "response_format": {"type": "json_object"}, "tool_choice": "none"},
        )
    if provider == "bedrock":
        raise ProviderNotConfigured("Bedrock is disabled; explicit access/cost review is required")
    raise ProviderNotConfigured("Unsupported AI provider")
