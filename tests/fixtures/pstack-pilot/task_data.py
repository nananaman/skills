import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    completed: bool


def load_tasks(path: Path) -> list[Task]:
    return [Task(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
