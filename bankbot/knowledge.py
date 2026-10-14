"""Load validated, team-authored fictional banking records."""
import json
from pathlib import Path


def load_records(path: Path, key: str) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError(f"{path.name}: expected a non-empty list")
    ids = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get(key), str):
            raise ValueError(f"{path.name}: missing {key}")
        if record[key] in ids:
            raise ValueError(f"{path.name}: duplicate {key}")
        ids.add(record[key])
    return records


def load_faq(path: Path) -> list[dict]:
    records = load_records(path, "faq_id")
    for record in records:
        for key in ("topic", "question", "answer", "source"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"{path.name}: invalid {key} in {record['faq_id']}")
        if not isinstance(record.get("aliases"), list) or any(
            not isinstance(x, str) or not x.strip() for x in record["aliases"]
        ):
            raise ValueError(f"{path.name}: invalid aliases")
    return records


class Knowledge:
    def __init__(self, data_dir: Path):
        self.faq = load_faq(data_dir / "faq.json")
        self.products = load_records(data_dir / "products.json", "product_name")
        self.branches = load_records(data_dir / "branches.json", "branch_id")
