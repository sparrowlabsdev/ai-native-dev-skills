"""Tools the model may request, and the registry that holds them.

To add a tool, write a function and decorate it with @tool. Project-specific
tools go in .relay/tools/*.py (that folder is off limits to the model) and are
loaded automatically:

    from relay.tools import tool

    @tool("terraform_plan", "Run terraform plan and return the summary.",
          args=[("dir", False, "directory, default '.'")])
    def terraform_plan(ctx, args, body):
        ...
        return "text shown to the model"
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import guard
from .guard import Refused


@dataclass
class Tool:
    name: str
    description: str
    args: list          # [(name, required, help)]
    body: str           # help text for the body, "" if the tool takes none
    mutating: bool
    fn: object

    def signature(self) -> str:
        parts = [f"{n}=<{h}>" if req else f"[{n}=<{h}>]" for n, req, h in self.args]
        text = f"- {self.name} {' '.join(parts)}".rstrip()
        if self.body:
            text += f"  (body: {self.body})"
        return f"{text}\n    {self.description}"


REGISTRY: dict = {}


def tool(name, description, args=(), body="", mutating=False):
    def register(fn):
        REGISTRY[name] = Tool(name, description, list(args), body, mutating, fn)
        return fn
    return register


class Context:
    """What a tool gets to work with."""

    def __init__(self, root: Path, policy: dict, session):
        self.root = root
        self.policy = policy
        self.session = session
        self.changed: list = []      # relative paths written or deleted this turn


def _tail(text: str, lines: int = 200) -> str:
    rows = text.splitlines()
    if len(rows) <= lines:
        return text
    return f"... ({len(rows) - lines} earlier lines omitted) ...\n" + "\n".join(rows[-lines:])


@tool("list_files", "List repository files (git-tracked and new files, minus ignored ones).",
      args=[("path", False, "directory to list, default the whole repository")])
def list_files(ctx, args, body):
    under = guard.safe_rel(ctx.root, args["path"], ctx.policy) if args.get("path") else ""
    files = guard.repo_files(ctx.root, ctx.policy, under)
    return "\n".join(files) if files else "(no files)"


@tool("read_file", "Return a file's content. Secret-looking, binary and very large files are withheld.",
      args=[("path", True, "file"), ("start", False, "first line"), ("end", False, "last line")])
def read_file(ctx, args, body):
    rel = guard.safe_rel(ctx.root, args.get("path", ""), ctx.policy)
    reason = guard.unreadable_reason(ctx.root, rel, ctx.policy)
    if reason:
        raise Refused(f"{rel}: withheld ({reason})")
    text = (ctx.root / rel).read_text(encoding="utf-8", errors="replace")
    if args.get("start") or args.get("end"):
        rows = text.splitlines()
        start = max(int(args.get("start", 1)), 1)
        end = min(int(args.get("end", len(rows))), len(rows))
        return "\n".join(f"{n}: {rows[n - 1]}" for n in range(start, end + 1))
    return text if text else "(empty file)"


@tool("search", "Search file contents with a regular expression. Returns path:line: text.",
      args=[("pattern", True, "regular expression"), ("path", False, "directory or file to limit to")])
def search(ctx, args, body):
    try:
        pattern = re.compile(args.get("pattern", ""))
    except re.error as exc:
        raise Refused(f"bad regular expression: {exc}")
    under = guard.safe_rel(ctx.root, args["path"], ctx.policy) if args.get("path") else ""
    hits = []
    for rel in guard.repo_files(ctx.root, ctx.policy, under):
        if guard.unreadable_reason(ctx.root, rel, ctx.policy):
            continue
        text = (ctx.root / rel).read_text(encoding="utf-8", errors="replace")
        for number, row in enumerate(text.splitlines(), 1):
            if pattern.search(row):
                hits.append(f"{rel}:{number}: {row.strip()[:200]}")
                if len(hits) >= 100:
                    return "\n".join(hits) + "\n(stopped at 100 matches; narrow the search)"
    return "\n".join(hits) if hits else "(no matches)"


@tool("git_diff", "Show changes as a unified diff: against a base branch or commit, "
                  "or uncommitted changes when no base is given. New files you wrote "
                  "in this same reply appear from the next turn.",
      args=[("base", False, "branch or commit to compare with"), ("path", False, "limit to a file or directory")])
def git_diff(ctx, args, body):
    cmd = ["git", "diff"]
    base = args.get("base", "")
    if base:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", base):
            raise Refused("base must be a plain branch name or commit id")
        known = subprocess.run(["git", "rev-parse", "--verify", "-q", base + "^{commit}"],
                               cwd=str(ctx.root), capture_output=True)
        if known.returncode != 0:
            raise Refused(f"unknown branch or commit: {base}")
        fork = subprocess.run(["git", "merge-base", base, "HEAD"], cwd=str(ctx.root),
                              capture_output=True, text=True).stdout.strip()
        cmd.append(fork or base)       # working tree against where this branch left base
    else:
        cmd.append("HEAD")
    cmd += ["--", guard.safe_rel(ctx.root, args["path"], ctx.policy) if args.get("path") else ".",
            ":!.relay", ":!.beads"]
    out = subprocess.run(cmd, cwd=str(ctx.root), capture_output=True, text=True).stdout
    if guard.SECRET_CONTENT.search(out):
        raise Refused("the diff looks like it contains a credential; ask the operator")
    limit = int(ctx.policy.get("max_file_kb", 200)) * 1024
    if len(out) > limit:
        return out[:limit] + "\n(diff truncated; pass path= to narrow it)"
    return out or "(no differences)"


@tool("write_file", "Create or replace a file with exactly the body you send.",
      args=[("path", True, "file")], body="the complete file content", mutating=True)
def write_file(ctx, args, body):
    rel = guard.safe_rel(ctx.root, args.get("path", ""), ctx.policy)
    target = ctx.root / rel
    existed = target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    ctx.changed.append(rel)
    return f"{'replaced' if existed else 'created'} {rel} ({len(body.splitlines())} lines)"


@tool("delete_file", "Delete a file.", args=[("path", True, "file")], mutating=True)
def delete_file(ctx, args, body):
    rel = guard.safe_rel(ctx.root, args.get("path", ""), ctx.policy)
    target = ctx.root / rel
    if not target.is_file():
        raise Refused(f"{rel}: not a file")
    target.unlink()
    ctx.changed.append(rel)
    return f"deleted {rel}"


@tool("run_check", "Run one of the project's named checks and return its output. "
                   "You choose a name; you cannot supply a command.",
      args=[("name", False, "check name, default 'default'")])
def run_check(ctx, args, body):
    name = args.get("name", "default")
    checks = {k: v for k, v in ctx.policy.get("checks", {}).items() if v}
    if name not in checks:
        available = ", ".join(sorted(checks)) or "none configured"
        raise Refused(f"no check named '{name}'. Available: {available}")
    timeout = int(ctx.policy.get("check_timeout_seconds", 900))
    try:
        done = subprocess.run(checks[name], shell=True, cwd=str(ctx.root), text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        code, output = done.returncode, done.stdout or ""
    except subprocess.TimeoutExpired as exc:
        code, output = 124, (exc.stdout or "") + f"\n(timed out after {timeout}s)"
    ctx.session.record_check(name, code == 0)
    verdict = "CHECK PASSED" if code == 0 else f"CHECK FAILED (exit code {code})"
    return f"{verdict}\n$ {checks[name]}\n{_tail(output)}"


@tool("ask", "Ask the operator a question when you cannot proceed without a decision.",
      body="the question")
def ask(ctx, args, body):
    if not body.strip():
        raise Refused("ask needs a question in the body")
    ctx.session.question = body.strip()
    return "question passed to the operator; their answer will arrive in the next turn"


@tool("finish", "Declare the task complete.", body="a summary of what changed and how it was verified")
def finish(ctx, args, body):
    checks = [c for c in ctx.policy.get("checks", {}).values() if c]
    if ctx.policy.get("require_passing_check", True) and checks and ctx.session.d.get("mutated") \
            and ctx.session.d.get("gate", True):
        if not ctx.session.check_is_current():
            raise Refused("finish refused: a check must pass after your last file change. Call run_check first")
    ctx.session.summary = body.strip() or "(no summary given)"
    return "accepted"


def load_plugins(root: Path) -> list:
    """Import .relay/tools/*.py so their @tool functions register."""
    loaded = []
    folder = root / ".relay" / "tools"
    if not folder.is_dir():
        return loaded
    for path in sorted(folder.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"relay_plugin_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(path.name)
    return loaded


def mode_for(name: str, policy: dict) -> str:
    return policy.get("tools", {}).get(name, policy.get("default_tool_mode", "ask"))


def describe(policy: dict) -> str:
    lines = [t.signature() for t in REGISTRY.values() if mode_for(t.name, policy) != "deny"]
    return "\n".join(lines)
