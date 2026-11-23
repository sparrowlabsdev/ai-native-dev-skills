"""The core loop: one session works one task, turn by turn.

    turn out -> driver -> model reply -> parse calls -> policy -> run tools
        ^                                                            |
        +------------------------ results ---------------------------+

State lives on disk under .relay/sessions/<id>/, so the loop can stop after any
turn (a person may be carrying the reply) and pick up in a later process.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import guard, protocol, tools
from .config import UserError, state_dir
from .drivers import make_driver
from .guard import Refused

ACTIVE, WAITING, NEEDS_INPUT, FINISHED, STOPPED = "active", "waiting", "needs_input", "finished", "stopped"


class Session:
    def __init__(self, root: Path, policy: dict, data: dict):
        self.root, self.policy, self.d = root, policy, data
        self.dir = state_dir(root) / "sessions" / data["id"]
        self.driver = make_driver(data["driver"], policy, root)
        self.assume_yes = False
        self.question = ""
        self.summary = ""

    # ------------------------------------------------------------ storage --

    @classmethod
    def create(cls, root, policy, task, skill, driver_name):
        base = state_dir(root) / "sessions"
        n = 1
        while (base / f"{task['id']}-{n}").exists():
            n += 1
        data = {
            "id": f"{task['id']}-{n}", "task": dict(task), "skill": skill or "",
            "driver": driver_name, "turn": 0, "status": ACTIVE, "branch": "", "base": "",
            "last_check": None, "dirty": False, "pending_out": "", "notes": [], "nudges": 0,
            "created": _now(),
        }
        session = cls(root, policy, data)
        (session.dir / "turns").mkdir(parents=True)
        session.save()
        (state_dir(root) / "current").write_text(data["id"], encoding="utf-8")
        session.log("session_start", task=task["id"], title=task.get("title", ""),
                    driver=driver_name, skill=skill or "")
        return session

    @classmethod
    def load(cls, root, policy, session_id=None):
        if not session_id:
            pointer = state_dir(root) / "current"
            if not pointer.is_file():
                raise UserError("no session yet. Run: relay start")
            session_id = pointer.read_text(encoding="utf-8").strip()
        path = state_dir(root) / "sessions" / session_id / "session.json"
        if not path.is_file():
            raise UserError(f"session not found: {session_id}")
        return cls(root, policy, json.loads(path.read_text(encoding="utf-8")))

    def save(self):
        (self.dir / "session.json").write_text(json.dumps(self.d, indent=2) + "\n", encoding="utf-8")

    def log(self, event, **data):
        row = {"ts": _now(), "t": round(time.time(), 3), "session": self.d["id"],
               "turn": self.d["turn"], "event": event}
        row.update(data)
        with (self.dir / "trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    # --------------------------------------------- properties tools reach --

    @property
    def turn(self):
        return self.d["turn"]

    @property
    def skill(self):
        return self.d["skill"]

    def record_check(self, name, ok):
        self.d["last_check"] = {"name": name, "ok": ok, "turn": self.turn}
        if ok:
            self.d["dirty"] = False
        self.log("check", name=name, ok=ok)

    def check_is_current(self):
        last = self.d["last_check"]
        return bool(last and last["ok"] and not self.d["dirty"])

    def transcript(self):
        parts = []
        for n in range(1, self.turn + 1):
            out, reply = self._turn_file(n, "out"), self._turn_file(n, "in")
            if out.is_file():
                parts.append(f"##### HARNESS TURN {n} #####\n{out.read_text(encoding='utf-8')}")
            if reply.is_file():
                parts.append(f"##### MODEL REPLY {n} #####\n{reply.read_text(encoding='utf-8')}")
        return "\n\n".join(parts) + "\n"

    def _turn_file(self, n, kind):
        return self.dir / "turns" / f"{n:03d}-{kind}.{'md' if kind == 'out' else 'txt'}"

    # ------------------------------------------------------------- turns ---

    def first_turn(self, with_paths=(), note=""):
        policy, root = self.policy, self.root
        checks = {k: v for k, v in policy.get("checks", {}).items() if v}
        lines = [
            "# RELAY TURN 1", "",
            f"Session: {self.d['id']}", "",
            "You are working on a software task through a harness called relay.", "",
            protocol.protocol_help(tools.describe(policy)), "",
            "## Checks", "",
        ]
        lines += [f"- {name}: `{cmd}`" for name, cmd in checks.items()] or ["(none configured)"]
        lines += ["", "## Task", "", _render_task(self.d["task"])]
        if note:
            lines += ["", "### Operator notes", "", note]
        if self.driver.injects_skill and self.skill:
            lines += ["", f"## Skill: {self.skill}", "", self._skill_text()]
        lines += ["", "## Repository", "", f"Branch: {_git(root, 'symbolic-ref', '--short', '-q', 'HEAD') or 'detached'}", ""]

        files = guard.repo_files(root, policy)
        wanted = []
        for raw in with_paths:
            rel = guard.safe_rel(root, raw, policy)
            wanted += [f for f in files if f == rel or f.startswith(rel.rstrip("/") + "/")]
        order = list(dict.fromkeys(wanted + files))
        budget = int(policy.get("preload_kb", 150)) * 1024
        preloaded, withheld, listed = [], [], []
        for rel in order:
            reason = guard.unreadable_reason(root, rel, policy)
            if reason:
                withheld.append(f"- {rel} ({reason})")
                continue
            size = (root / rel).stat().st_size
            if rel in wanted or size <= budget:
                budget -= size
                preloaded.append(rel)
            else:
                listed.append(rel)
        lines += ["### Files", ""] + ([f"- {f}" for f in files] or ["(empty repository)"])
        if preloaded:
            lines += ["", "### File contents already loaded", ""]
            for rel in preloaded:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
                lines += [f"===== FILE: {rel} =====", text.rstrip("\n"), "===== END FILE =====", ""]
        if listed:
            lines += ["", "### Not loaded (use read_file)", ""] + [f"- {f}" for f in listed]
        if withheld:
            lines += ["", "### Withheld", "", "Content of these is not available to you:", ""] + withheld
        return "\n".join(lines) + "\n"

    def _skill_text(self):
        folder = self.policy.get("skills_dir") or str(Path(__file__).resolve().parent.parent / "skills")
        path = Path(folder) / self.skill / "SKILL.md"
        if not path.is_file():
            raise UserError(f"skill not found: {path}")
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            text = text.split("---", 2)[2]
        return text.strip()

    def run(self, outbound):
        """Send turns until the driver has to wait or the session ends."""
        while True:
            if self.turn >= int(self.policy.get("max_turns", 40)):
                self._end(STOPPED, f"stopped at the turn limit ({self.turn})")
                return
            self.d["turn"] += 1
            if self.d["notes"]:
                outbound += "\n## Operator notes\n\n" + "\n\n".join(self.d["notes"]) + "\n"
                self.d["notes"] = []
            turn_file = self._turn_file(self.turn, "out")
            turn_file.write_text(outbound, encoding="utf-8")
            self.d["status"] = WAITING
            self.save()
            self.log("turn_out", bytes=len(outbound.encode("utf-8")))
            reply = self.driver.send(self, outbound, turn_file)
            if reply is None:
                return
            outbound = self.advance(reply)
            if outbound is None:
                return

    def feed(self, reply, operator_message=""):
        """Take a reply carried in by the operator and continue."""
        if self.d["status"] != WAITING:
            raise UserError(f"session {self.d['id']} is {self.d['status']}, not waiting for a reply")
        if operator_message:
            self.d["notes"].append(operator_message)
        outbound = self.advance(reply)
        if outbound is not None:
            self.run(outbound)

    def say(self, text):
        if self.d["status"] != NEEDS_INPUT:
            raise UserError("the model has not asked a question. Use: relay step --say \"...\"")
        outbound = self.d["pending_out"] + f"\n## Operator answer\n\n{text}\n\n{protocol.REMINDER}\n"
        self.d["pending_out"] = ""
        self.log("operator_answer", chars=len(text))
        self.run(outbound)

    def advance(self, reply):
        """Process one model reply. Returns the next outbound turn, or None."""
        body_tools = {t.name for t in tools.REGISTRY.values() if t.body}
        calls = protocol.parse_calls(reply, body_tools)
        if not calls:
            if self.driver.interactive:
                raise UserError("no '=== CALL ... ===' lines found in the reply. "
                                "Copy the whole code block from the chat and try again")
            self.d["nudges"] += 1
            if self.d["nudges"] > 2:
                self._end(STOPPED, "the model stopped using the protocol")
                return None
            self._turn_file(self.turn, "in").write_text(reply, encoding="utf-8")
            return f"# RELAY TURN {self.turn + 1}\n\nNo tool calls were found in your reply.\n\n{protocol.REMINDER}\n"

        if any(c.name in tools.REGISTRY and tools.REGISTRY[c.name].mutating for c in calls):
            self._prepare_branch()
        self._turn_file(self.turn, "in").write_text(reply, encoding="utf-8")
        self.d["status"] = ACTIVE
        self.log("turn_in", calls=len(calls), bytes=len(reply.encode("utf-8")))

        ctx = tools.Context(self.root, self.policy, self)
        results = []
        for index, call in enumerate(calls, 1):
            status, output = self._execute(ctx, call)
            results.append(protocol.render_result(index, call, status, output))
            print(f"  [{status:>7}] {call.label()[:100]}")
        self._commit(ctx.changed)

        if self.summary:
            self._end(FINISHED, self.summary)
            return None

        last = self.d["last_check"]
        state = "not run yet" if not last else (
            f"{last['name']} {'PASSED' if last['ok'] else 'FAILED'}"
            + (", but files changed since" if last["ok"] and self.d["dirty"] else ""))
        outbound = (f"# RELAY TURN {self.turn + 1}\n\n## Results\n\n" + "\n".join(results)
                    + f"\n## Status\n\nLast check: {state}.\n")
        if self.question:
            self.d["status"], self.d["pending_out"] = NEEDS_INPUT, outbound
            self.save()
            self.log("question", text=self.question)
            print(f"\nThe model asks:\n\n{self.question}\n\nAnswer with: relay say \"<your answer>\"")
            return None
        self.save()
        return outbound + f"\n{protocol.REMINDER}\n"

    # ------------------------------------------------------------- tools ---

    def _execute(self, ctx, call):
        started = time.time()
        status, output = self._execute_inner(ctx, call)
        self.log("tool", name=call.name, args=call.args, status=status,
                 ms=int((time.time() - started) * 1000), body_bytes=len(call.body.encode("utf-8")))
        return status, output

    def _execute_inner(self, ctx, call):
        if call.error:
            return "error", call.error
        spec = tools.REGISTRY.get(call.name)
        if not spec or tools.mode_for(call.name, self.policy) == "deny":
            return "error", f"unknown tool '{call.name}'. Use only the tools listed in turn 1"
        missing = [n for n, required, _ in spec.args if required and not call.args.get(n)]
        if missing:
            return "error", f"missing argument(s): {', '.join(missing)}"
        if not self._approved(spec, call):
            return "denied", "the operator did not approve this call"
        try:
            output = spec.fn(ctx, call.args, call.body)
        except Refused as exc:
            return "refused", str(exc)
        except Exception as exc:  # a tool bug must not kill the session
            return "error", f"{type(exc).__name__}: {exc}"
        if spec.mutating:
            self.d["dirty"] = self.d["mutated"] = True
        return "ok", output

    def _approved(self, spec, call):
        if tools.mode_for(spec.name, self.policy) == "auto" or self.assume_yes:
            return True
        detail = call.label()
        if spec.name == "run_check":
            name = call.args.get("name", "default")
            detail += f"  ->  {self.policy.get('checks', {}).get(name, '(unknown check)')}"
        if not sys.stdin.isatty():
            print(f"  needs approval (rerun with --yes to allow): {detail}")
            return False
        answer = input(f"  Allow {detail} ? [y/N] ").strip().lower()
        self.log("approval", name=spec.name, allowed=answer in ("y", "yes"))
        return answer in ("y", "yes")

    # --------------------------------------------------------------- git ---

    def _prepare_branch(self):
        root = self.root
        if subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=str(root),
                          capture_output=True).returncode != 0:
            raise UserError("make an initial commit first, so changes can be reviewed and undone")
        current = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
        if self.d["branch"] and current == self.d["branch"]:
            return
        dirty = _git(root, "status", "--porcelain", "--untracked-files=no", "--", ".", ":!.relay")
        if dirty:
            raise UserError("uncommitted changes in the working tree. Commit or stash them first, "
                            "so the model's changes stay separate from yours")
        if not self.d["branch"]:
            self.d["base"] = current or _git(root, "rev-parse", "--short", "HEAD")
            self.d["branch"] = self.policy.get("branch_prefix", "relay/") + self.d["task"]["id"]
        exists = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{self.d['branch']}"],
                                cwd=str(root), capture_output=True).returncode == 0
        args = ["checkout", "-q", self.d["branch"]] if exists else ["checkout", "-q", "-b", self.d["branch"]]
        done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)
        if done.returncode != 0:
            raise UserError(f"could not switch to {self.d['branch']}: {done.stderr.strip()}")
        self.save()

    def _commit(self, changed):
        if not changed or not self.policy.get("commit_each_turn", True):
            return
        paths = sorted(set(changed))
        subprocess.run(["git", "add", "-A", "--", *paths], cwd=str(self.root), capture_output=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(self.root)).returncode == 0:
            return
        message = f"relay {self.d['task']['id']} turn {self.turn}: model output (unreviewed)"
        done = subprocess.run(["git", "commit", "-q", "-m", message, "-m",
                               f"Session {self.d['id']}. Review before merging."],
                              cwd=str(self.root), capture_output=True, text=True)
        if done.returncode != 0:
            print(f"  warning: commit failed: {done.stderr.strip()}")
            return
        sha = _git(self.root, "rev-parse", "--short", "HEAD")
        self.log("commit", sha=sha, files=paths)
        print(f"  committed {len(paths)} file(s) as {sha} on {self.d['branch']}")

    def _end(self, status, text):
        self.d["status"] = status
        self.save()
        self.log("session_end", status=status, summary=text)
        if status == FINISHED:
            print(f"\nThe model reports the task complete:\n\n{text}\n")
            if self.d["branch"]:
                print(f"Review: git log {self.d['base']}..{self.d['branch']}  and  git diff {self.d['base']}...{self.d['branch']}")
            print("When you have merged it: relay close")
        else:
            print(f"\nSession {status}: {text}")


def _render_task(task):
    parts = [f"Task {task['id']}: {task.get('title', '')}"]
    if task.get("description"):
        parts += ["", "Description:", task["description"]]
    if task.get("acceptance"):
        parts += ["", "Acceptance criteria:", task["acceptance"]]
    return "\n".join(parts)


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True).stdout.strip()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
