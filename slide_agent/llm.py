"""Thin, resilient wrapper around the OpenAI SDK.

Design goals:
- Bring-your-own-key: the key lives only in memory for the session.
- Works with any OpenAI-compatible endpoint (OpenAI, Azure gateways, Groq, OpenRouter, ...)
  via an optional base_url.
- Robust JSON output: JSON mode when the model supports it, with automatic fallback and
  fence-stripping when it does not.
- Graceful degradation: parameters not supported by a model (e.g. temperature on some
  reasoning models) are dropped and the call retried instead of failing.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

DEFAULT_MODEL = "gpt-4o-mini"


def parse_json_loose(text: str) -> Dict[str, Any]:
    """Parse JSON from an LLM response, tolerating code fences and stray prose."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError(f"Model did not return valid JSON. First 200 chars:\n{text[:200]}")


class LLMClient:
    """A small client used by every agent in the pipeline."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        base_url: Optional[str] = None,
        temperature: Optional[float] = 0.7,
        timeout: float = 120.0,
    ):
        api_key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise ValueError(
                "No OpenAI API key provided. Paste one in the sidebar or set OPENAI_API_KEY."
            )
        base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")).strip() or None
        self.model = (model or DEFAULT_MODEL).strip()
        self.temperature = temperature
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2)
        # Cumulative token accounting for the session (shown in the UI).
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    # ------------------------------------------------------------------ helpers
    def ping(self) -> str:
        """Cheap connectivity/auth check. Returns a human-readable status string."""
        try:
            self.client.models.list()
            return "ok"
        except AuthenticationError as e:
            raise AuthenticationError(
                message="API key was rejected. Double-check the key (and org/project).",
                response=e.response, body=e.body,
            ) from e
        except Exception:
            # Some gateways block model listing; assume reachable and let real calls decide.
            return "ok (model listing not permitted on this endpoint)"

    def _record_usage(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if u is not None:
            self.usage["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
            self.usage["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
        self.usage["calls"] += 1

    # ------------------------------------------------------------------ core call
    def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = True,
        temperature: Optional[float] = None,
    ) -> str:
        """One chat completion with adaptive parameter fallback."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages}
        temp = self.temperature if temperature is None else temperature
        if temp is not None:
            kwargs["temperature"] = float(temp)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_err: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                self._record_usage(resp)
                return resp.choices[0].message.content or ""
            except BadRequestError as e:
                msg = str(e).lower()
                # Drop unsupported params and retry (reasoning models, older gateways, ...)
                if "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature"); last_err = e; continue
                if "response_format" in msg and "response_format" in kwargs:
                    kwargs.pop("response_format"); last_err = e; continue
                raise
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                last_err = e
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after retries: {last_err}")

    def complete_json(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        retries: int = 2,
    ) -> Dict[str, Any]:
        """Chat completion that must return a JSON object; retries with the parse error appended."""
        attempt_user = user
        last: Optional[Exception] = None
        for _ in range(retries + 1):
            text = self.complete(system, attempt_user, json_mode=True, temperature=temperature)
            try:
                return parse_json_loose(text)
            except (ValueError, json.JSONDecodeError) as e:
                last = e
                attempt_user = (
                    user
                    + "\n\nYour previous reply was not valid JSON "
                    + f"({e}). Reply again with ONLY a valid JSON object."
                )
        raise ValueError(f"Could not obtain valid JSON from the model: {last}")
