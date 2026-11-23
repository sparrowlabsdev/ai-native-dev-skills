"""Policy and paths. Policy is plain JSON in .relay/policy.json."""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

STATE_DIR = ".relay"

DEFAULT_POLICY = {
    # Named commands that prove a change works. The model picks a name; it can
    # never supply a command of its own.
    "checks": {},
    "check_timeout_seconds": 900,
    # A session may only finish after a check has passed since the last change.
    "require_passing_check": True,
    # Per-tool mode: "auto" runs without asking, "ask" needs the operator's
    # approval each time, "deny" is never run. Tools not listed use the default.
    "tools": {
        "list_files": "auto",
        "read_file": "auto",
        "search": "auto",
        "git_diff": "auto",
        "write_file": "auto",
        "delete_file": "auto",
        "run_check": "ask",
        "ask": "auto",
        "finish": "auto",
    },
    "default_tool_mode": "ask",
    # What the model may see.
    "max_file_kb": 200,
    "preload_kb": 150,
    "secret_name_globs": [],     # added to the built-in list
    "allow_name_globs": [],      # let these through despite the secret filter
    "deny_path_globs": [],       # never read or written
    # Git handling for changes.
    "branch_prefix": "relay/",
    "commit_each_turn": True,
    # Loop limits.
    "max_turns": 40,
    # How turns reach the model.
    "default_driver": "manual",
    "drivers": {
        "manual": {},
        # Example: any program that reads the transcript on stdin and prints
        # the model's reply. Swap this in when a CLI or API is available.
        "command": {"cmd": [], "timeout_seconds": 600},
    },
    # Where SKILL.md folders live, for drivers that must inject the skill text.
    "skills_dir": "",
}


class UserError(Exception):
    """A problem the operator can fix; shown without a traceback."""


def repo_root(start: Path | None = None) -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start or Path.cwd()), capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise UserError("run this inside a git repository (git init first)")
    return Path(out)


def state_dir(root: Path) -> Path:
    return root / STATE_DIR


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_policy(root: Path) -> dict:
    policy = copy.deepcopy(DEFAULT_POLICY)
    path = state_dir(root) / "policy.json"
    if path.is_file():
        try:
            _merge(policy, json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise UserError(f"{path} is not valid JSON: {exc}")
    return policy


def write_default_policy(root: Path) -> Path:
    directory = state_dir(root)
    directory.mkdir(exist_ok=True)
    path = directory / "policy.json"
    if not path.exists():
        starter = {
            "checks": {"default": ""},
            "tools": DEFAULT_POLICY["tools"],
            "default_driver": "manual",
        }
        path.write_text(json.dumps(starter, indent=2) + "\n", encoding="utf-8")
    ignore = directory / ".gitignore"
    if not ignore.exists():
        ignore.write_text("current\n", encoding="utf-8")
    return path
