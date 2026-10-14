"""Small DeepSeek Chat Completions adapter using Python's standard HTTP library."""
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse


class APIError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DeepSeekClient:
    def __init__(self, settings):
        self.settings = settings

    def complete(self, messages, tools=None, timeout=None):
        settings = self.settings
        if not settings.api_key:
            raise APIError("missing_key", "Configure DEEPSEEK_API_KEY or use offline mode.")
        parsed = urlparse(settings.base_url)
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise APIError("invalid_url", "The API base URL must use HTTPS.")
        payload = {"model": settings.model, "messages": messages, "max_tokens": settings.max_tokens,
                   "stream": False, "thinking": {"type": "disabled"}}
        if tools:
            payload["tools"] = tools
        req = Request(settings.base_url.rstrip("/") + "/chat/completions",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": "Bearer " + settings.api_key, "Content-Type": "application/json"})
        started = time.monotonic()
        try:
            with urlopen(req, timeout=timeout or settings.timeout_seconds) as response:
                data = json.load(response)
            message = data["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("Invalid message")
            if message.get("content") is not None and not isinstance(message["content"], str):
                raise ValueError("Invalid content")
            if message.get("tool_calls") is not None and not isinstance(message["tool_calls"], list):
                raise ValueError("Invalid tool list")
            # Preserve provider-supplied reasoning/tool fields for subsequent requests.
            allowed = ("role", "content", "tool_calls", "reasoning_content")
            message = {k: v for k, v in message.items() if k in allowed}
            message["role"] = "assistant"
            if not message.get("content") and not message.get("tool_calls"):
                raise APIError("empty_response", "The API returned an empty answer.")
            return {"message": message, "usage": data.get("usage", {}),
                    "latency_ms": round((time.monotonic() - started) * 1000)}
        except HTTPError as exc:
            # Do not expose the provider's raw body, headers, or key in UI/logs.
            labels = {401: "Invalid API credentials.", 402: "API balance is insufficient.",
                      429: "API rate limit reached.", 500: "API server error.", 503: "API service unavailable."}
            raise APIError(f"http_{exc.code}", labels.get(exc.code, f"API request failed (HTTP {exc.code}).")) from None
        except (TimeoutError, URLError, OSError) as exc:
            raise APIError("network_error", "The API could not be reached within the time limit.") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise APIError("invalid_response", "The API response format was not recognised.") from None
