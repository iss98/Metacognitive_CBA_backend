from functools import lru_cache

from ..config import get_settings


@lru_cache
def get_chat_model():
    """Return a LangChain chat model only when the researcher enables one.

    The MVP defaults to mock mode so no credential is required and no student data
    leaves the local machine accidentally.
    """

    settings = get_settings()
    if settings.llm_provider == "openai":
        if not settings.openai_api_key or not settings.openai_chat_model:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_CHAT_MODEL are required")
        from langchain_openai import ChatOpenAI

        model_options = {
            "model": settings.openai_chat_model,
            "api_key": settings.openai_api_key,
        }
        if settings.openai_chat_model.startswith("gpt-6"):
            model_options["reasoning_effort"] = settings.openai_reasoning_effort
            if settings.openai_reasoning_effort == "none":
                model_options["temperature"] = 0
        else:
            model_options["temperature"] = 0

        return ChatOpenAI(
            **model_options,
        )
    if settings.llm_provider == "google":
        if not settings.gemini_model:
            raise RuntimeError("GEMINI_MODEL is required")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.gemini_model, temperature=0)
    return None

