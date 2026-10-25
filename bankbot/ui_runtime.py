"""Invalidate backend caches on source/data changes and tolerate legacy replies."""
import hashlib
import importlib
from .config import ROOT
from .language import detect_language


def source_revision():
    digest = hashlib.sha256()
    for path in sorted(list((ROOT / "bankbot").glob("*.py")) + list((ROOT / "data").glob("*.json"))):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_service(settings):
    # Page reruns can retain imported backend classes. Reload in dependency order.
    for name in ("language", "knowledge", "dialogue", "retrieval", "tools", "llm_client", "service"):
        importlib.reload(importlib.import_module("bankbot." + name))
    return importlib.import_module("bankbot.service").ChatService(settings)


def reply_details(reply, user_text, previous_language="en"):
    return {"mode": reply.mode,
        "response_language": getattr(reply, "language", None) or detect_language(user_text, previous_language),
        "source_ids": getattr(reply, "source_ids", []),
        "tool_calls": [{"name": t.get("name", ""), "arguments": t.get("arguments", {})} for t in getattr(reply, "tools", [])],
        "latency_ms": getattr(reply, "latency_ms", 0), "api_calls": getattr(reply, "api_calls", 0),
        "usage": getattr(reply, "usage", {}), "error": getattr(reply, "error", None),
        "language_corrections": getattr(reply, "language_corrections", 0),
        "followups":getattr(reply,'followups',[]),"sources":getattr(reply,'sources',[]),"consistency_corrections":getattr(reply,'consistency_corrections',0)}
