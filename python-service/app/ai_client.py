from typing import Optional
import threading
import time
from collections import deque
import re

import google.generativeai as genai

from .config import settings

_AI_CALL_LOCK = threading.Lock()
_LAST_AI_CALL_TS = 0.0
_MIN_AI_CALL_INTERVAL_SECONDS = 6.0
_RPM_WINDOW_SECONDS = 60.0
_RPM_LIMIT = 9
_AI_CALL_TIMESTAMPS = deque()


def _extract_text(response) -> str:
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    parts = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            value = getattr(part, "text", None)
            if value:
                parts.append(value)
    return "\n".join(parts).strip()


def generate_text(
    prompt: str,
    *,
    temperature: float = 0.1,
    max_output_tokens: int = 256,
    model: Optional[str] = None,
) -> str:
    global _LAST_AI_CALL_TS
    api_key = settings.google_api_key or ""
    if not api_key.strip():
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    # Global process-level throttle + rolling RPM gate to avoid free-tier bursts.
    with _AI_CALL_LOCK:
        now = time.monotonic()

        # Drop timestamps outside the rolling minute window.
        while _AI_CALL_TIMESTAMPS and (now - _AI_CALL_TIMESTAMPS[0]) >= _RPM_WINDOW_SECONDS:
            _AI_CALL_TIMESTAMPS.popleft()

        # If we're at RPM cap, wait until the oldest call rolls off.
        if len(_AI_CALL_TIMESTAMPS) >= _RPM_LIMIT:
            wait_for_window = _RPM_WINDOW_SECONDS - (now - _AI_CALL_TIMESTAMPS[0]) + 0.1
            if wait_for_window > 0:
                time.sleep(wait_for_window)
            now = time.monotonic()
            while _AI_CALL_TIMESTAMPS and (now - _AI_CALL_TIMESTAMPS[0]) >= _RPM_WINDOW_SECONDS:
                _AI_CALL_TIMESTAMPS.popleft()

        wait_seconds = _MIN_AI_CALL_INTERVAL_SECONDS - (now - _LAST_AI_CALL_TS)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _LAST_AI_CALL_TS = time.monotonic()
        _AI_CALL_TIMESTAMPS.append(_LAST_AI_CALL_TS)

    model_name = model or settings.gemini_model
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model_name)
    attempts = 0
    max_attempts = 2
    while True:
        attempts += 1
        try:
            response = client.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )
            break
        except Exception as e:
            error_text = str(e)
            if attempts >= max_attempts:
                raise RuntimeError(f"Gemini request failed for model '{model_name}': {e}") from e
            # Fast-fail retry policy: retry once after 1 second.
            time.sleep(1.0)
    text = _extract_text(response)
    if not text:
        raise RuntimeError("Gemini response did not include text.")
    return text
