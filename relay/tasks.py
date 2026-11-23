"""Where tasks come from.

Beads (the bd CLI) when it is installed and the repository has .beads/;
otherwise a small JSON file. Both expose the same few methods, so another
tracker can be added the same way.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
from pathlib import Path

from .config import UserError, state_dir


class Task(dict):
    """id, title, description, acceptance."""

    def render(self) -> str:
        parts = [f"Task {self['id']}: {self['title']}"]
        if self.get("description"):
            parts += ["", "Description:", self["description"]]
        if self.get("acceptance"):
            parts += ["", "Acceptance criteria:", self["acceptance"]]
        return "\n".join(parts)


class BeadsTasks:
    name = "beads"

    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def available(root: Path) -> bool:
        return shutil.which("bd") is not None and (root / ".beads").is_dir()

    def _bd(self, *args, check=True) -> str:
        done = subprocess.run(["bd", *args], cwd=str(self.root), capture_output=True, text=True)
        if check and done.returncode != 0:
            raise UserError(f"bd {' '.join(args)} failed: {(done.stderr or done.stdout).strip()}")
        return done.stdout

    def _from_json(self, raw: str):
        data = json.loads(raw)
        item = data[0] if isinstance(data, list) and data else data
        if not item:
            return None
        return Task(id=item["id"], title=item.get("title", ""),
                    description=item.get("description", ""),
                    acceptance=item.get("acceptance_criteria", ""))

    def get(self, task_id: str) -> Task:
        task = self._from_json(self._bd("show", task_id, "--json"))
        if not task:
            raise UserError(f"bead not found: {task_id}")
        return task

    def next(self):
        task = self._from_json(self._bd("ready", "--json"))
        if task:
            self._bd("update", task["id"], "--claim", check=False)
        return task

    def create(self, title: str, description: str = "") -> Task:
        args = ["create", title, "--silent"]
        if description:
            args += ["-d", description]
        return self.get(self._bd(*args).strip())

    def close(self, task_id: str, reason: str) -> None:
        self._bd("close", task_id, "--reason", reason)

    def load_plan(self, path: Path) -> str:
        return self._bd("create", "--graph", str(path), "--json")


class LocalTasks:
    name = "local"

    def __init__(self, root: Path):
        self.path = state_dir(root) / "tasks.json"

    def _load(self) -> list:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else []

    def _save(self, tasks: list) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")

    def get(self, task_id: str) -> Task:
        for item in self._load():
            if item["id"] == task_id:
                return Task(item)
        raise UserError(f"task not found: {task_id}")

    def next(self):
        for item in self._load():
            if item.get("status", "open") == "open":
                return Task(item)
        return None

    def create(self, title: str, description: str = "") -> Task:
        tasks = self._load()
        item = {"id": f"local-{secrets.token_hex(2)}", "title": title,
                "description": description, "acceptance": "", "status": "open"}
        tasks.append(item)
        self._save(tasks)
        return Task(item)

    def close(self, task_id: str, reason: str) -> None:
        tasks = self._load()
        for item in tasks:
            if item["id"] == task_id:
                item["status"], item["closed_reason"] = "closed", reason
        self._save(tasks)

    def load_plan(self, path: Path) -> str:
        raise UserError("loading a plan needs Beads: install bd and run 'bd init' here")


def task_source(root: Path):
    return BeadsTasks(root) if BeadsTasks.available(root) else LocalTasks(root)
