from google import genai
from google.genai import types

from app.settings import settings

client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None


def embed(text: str) -> list[float] | None:
    """768 numbers that represent the meaning of `text`, or None if Gemini is unavailable."""
    if client is None:
        return None
    try:
        result = client.models.embed_content(
            model=settings.gemini_embed_model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        return list(result.embeddings[0].values)
    except Exception as e:
        print("embedding failed:", e)
        return None