
import asyncio
import time

from google import genai

from app.core.config import settings


def _generate_text(prompt: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing from .env")

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY
    )

    retry_delays = [2, 5]

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )

            generated_text = response.text

            if not generated_text:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return generated_text.strip()

        except Exception as exc:
            error_message = str(exc)

            temporary_error = (
                "503" in error_message
                or "UNAVAILABLE" in error_message
            )

            if not temporary_error:
                raise RuntimeError(
                    f"Gemini API request failed: {error_message}"
                ) from exc

            if attempt == 2:
                raise RuntimeError(
                    "Gemini is temporarily unavailable after "
                    "3 attempts. Please try again later."
                ) from exc

            wait_seconds = retry_delays[attempt]

            print(
                f"Gemini temporarily unavailable. "
                f"Retrying in {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)

    raise RuntimeError("Gemini generation failed.")


async def generate_gemini_text(prompt: str) -> str:
    return await asyncio.to_thread(
        _generate_text,
        prompt,
    )
