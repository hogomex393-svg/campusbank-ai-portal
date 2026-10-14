"""Local persistence and recovery of interrupted UI histories."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import json
import os
import uuid
from .dialogue import coerce_state


def conversation_id(value=None):
    try:
        return uuid.UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid4().hex


def repair_display(display, state):
    """Recover replies that reached backend state before an old UI crashed."""
    display = deepcopy(display or [])
    recovered = []
    for turn in coerce_state(state).turns:
        users = [m for m in turn if m.get("role") == "user"]
        assistants = [m for m in turn if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"].strip()]
        if users:
            recovered.append({"role": "user", "content": users[0]["content"]})
        if assistants:
            recovered.append({"role": "assistant", "content": assistants[-1]["content"]})
    if not recovered:
        return display
    positions = [i for i, m in enumerate(display) if m.get("role") == "user"]
    recovered_users = [m["content"] for m in recovered if m["role"] == "user"]
    visible_users = [display[i]["content"] for i in positions]
    if len(visible_users) >= len(recovered_users) and visible_users[-len(recovered_users):] == recovered_users:
        start = positions[len(visible_users) - len(recovered_users)]
        suffix = display[start:]
        if [(m["role"], m["content"]) for m in suffix] == [(m["role"], m["content"]) for m in recovered]:
            return display
        return display[:start] + recovered
    return recovered if not display else display


class HistoryStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def load(self, id_):
        try:
            id_ = uuid.UUID(str(id_)).hex
            record = json.loads((self.folder / (id_ + ".json")).read_text(encoding="utf-8"))
            if not isinstance(record.get("display"), list) or not isinstance(record.get("state"), dict):
                return None
            return record
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def save(self, id_, state, display):
        id_ = uuid.UUID(str(id_)).hex
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / (id_ + ".json")
        tmp = self.folder / (id_ + "." + uuid.uuid4().hex + ".tmp")
        record = {"schema": 2, "state": asdict(coerce_state(state)), "display": display}
        try:
            tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
