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

    def complete_stream(self,messages,tools=None,timeout=None,on_delta=None):
        return self.complete(messages,tools,timeout,on_delta=on_delta)

    def complete(self, messages, tools=None, timeout=None,on_delta=None):
        settings = self.settings
        if not settings.api_key:
            raise APIError("missing_key", "Configure DEEPSEEK_API_KEY or use offline mode.")
        parsed = urlparse(settings.base_url)
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise APIError("invalid_url", "The API base URL must use HTTPS.")
        wire_messages=messages if settings.provider=='deepseek' else [{k:v for k,v in m.items() if k!='reasoning_content'} for m in messages]
        payload = {"model": settings.model, "messages": wire_messages, "max_tokens": settings.max_tokens,
                   "stream": False}
        if settings.provider=='deepseek':payload['thinking']={'type':'disabled'}
        elif settings.provider=='qwen':payload['enable_thinking']=False
        if tools:
            payload["tools"] = tools
        if on_delta is not None:
            payload.update(stream=True,stream_options={'include_usage':True})
        req = Request(settings.base_url.rstrip("/") + "/chat/completions",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": "Bearer " + settings.api_key, "Content-Type": "application/json"})
        started = time.monotonic()
        try:
            with urlopen(req, timeout=timeout or settings.timeout_seconds) as response:
                data = self._read_stream(response,on_delta,started+(timeout or settings.timeout_seconds)) if on_delta is not None else json.load(response)
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

    @staticmethod
    def _read_stream(response,on_delta,deadline):
        content=[];reasoning=[];calls={};usage={};finished=False
        for raw in response:
            if time.monotonic()>deadline:raise APIError('timeout','The streamed response exceeded its time budget.')
            line=raw.decode('utf-8').strip()
            if not line.startswith('data:'):continue
            value=line[5:].strip()
            if value=='[DONE]':finished=True;break
            packet=json.loads(value)
            if packet.get('error'):raise APIError('invalid_response','The provider interrupted the streamed answer.')
            if isinstance(packet.get('usage'),dict):usage=packet['usage']
            choices=packet.get('choices') or []
            if not choices:continue
            choice=choices[0];delta=choice.get('delta') or {}
            if choice.get('finish_reason'):finished=True
            text=delta.get('content')
            if text:
                if not isinstance(text,str):raise ValueError('Invalid text delta')
                content.append(text);on_delta(text)
            if isinstance(delta.get('reasoning_content'),str):reasoning.append(delta['reasoning_content'])
            for item in delta.get('tool_calls') or []:
                index=item.get('index',0)
                if not isinstance(index,int) or not 0<=index<6:raise ValueError('Invalid tool index')
                call=calls.setdefault(index,{'id':'','type':'function','function':{'name':'','arguments':''}})
                if item.get('id'):call['id']+=item['id']
                function=item.get('function') or {}
                for key in ('name','arguments'):
                    if function.get(key):call['function'][key]+=function[key]
        if not finished:raise APIError('incomplete_stream','The answer stream ended before completion.')
        message={'role':'assistant','content':''.join(content) or None}
        if calls:message['tool_calls']=[calls[i] for i in sorted(calls)]
        if reasoning:message['reasoning_content']=''.join(reasoning)
        return {'choices':[{'message':message}],'usage':usage}
