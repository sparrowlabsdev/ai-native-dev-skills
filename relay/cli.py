"""Command line for relay."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__, tools
from .config import UserError, load_policy, repo_root, state_dir, write_default_policy
from .drivers import DRIVERS, read_clipboard
from .session import FINISHED, Session
from .tasks import task_source


def _setup():
    root = repo_root()
    policy = load_policy(root)
    plugins = tools.load_plugins(root)
    return root, policy, plugins


def cmd_init(args):
    root = repo_root()
    path = write_default_policy(root)
    print(f"Wrote {path.relative_to(root)}")
    if shutil.which("bd"):
        print("Beads: " + ("found .beads/, tasks will be beads." if (root / ".beads").is_dir()
                           else "bd is installed; run 'bd init' here to track tasks as beads."))
    else:
        print("Beads: bd is not installed, so tasks are kept in .relay/tasks.json.")
    print('Next: set checks.default in the policy file, then: relay start --title "<task>"')


def cmd_start(args):
    root, policy, _ = _setup()
    source = task_source(root)
    if args.task:
        task = source.get(args.task)
    elif args.title:
        task = source.create(args.title, args.description or "")
    elif args.next:
        task = source.next()
        if not task:
            raise UserError("no ready tasks")
    else:
        raise UserError('say which task: a task id, --next, or --title "<new task>"')
    driver_name = args.driver or policy.get("default_driver", "manual")
    session = Session.create(root, policy, task, args.skill, driver_name)
    session.d["gate"] = not args.no_check_gate
    session.assume_yes = args.yes
    print(f"Session {session.d['id']}: {task['title']}  (driver: {driver_name}, tasks: {source.name})")
    session.run(session.first_turn(args.with_paths or [], args.note or ""))


def cmd_step(args):
    root, policy, _ = _setup()
    session = Session.load(root, policy, args.session)
    session.assume_yes = args.yes
    if args.paste:
        reply = read_clipboard()
    elif args.file == "-":
        reply = sys.stdin.read()
    elif args.file:
        reply = Path(args.file).read_text(encoding="utf-8")
    else:
        raise UserError("give the reply: --paste, a file path, or - for stdin")
    session.feed(reply, args.say or "")


def cmd_say(args):
    root, policy, _ = _setup()
    session = Session.load(root, policy, args.session)
    session.assume_yes = args.yes
    session.say(args.text)


def cmd_check(args):
    """Operator runs a named check; the output goes to the model next turn."""
    root, policy, _ = _setup()
    session = Session.load(root, policy, args.session)
    ctx = tools.Context(root, policy, session)
    output = tools.REGISTRY["run_check"].fn(ctx, {"name": args.name}, "")
    session.d["notes"].append(f"The operator ran check '{args.name}':\n\n{output}")
    session.save()
    print(output)
    print("\nThis output will be included in the next turn sent to the model.")


def cmd_close(args):
    root, policy, _ = _setup()
    session = Session.load(root, policy, args.session)
    if session.d["status"] != FINISHED and not args.force:
        raise UserError(f"session is {session.d['status']}, not finished. Use --force to close anyway")
    reason = args.reason or f"Completed via relay session {session.d['id']} in {session.turn} turn(s)"
    task_source(root).close(session.d["task"]["id"], reason)
    session.log("task_closed", reason=reason)
    print(f"Closed {session.d['task']['id']}.")


def cmd_plan(args):
    root, _, _ = _setup()
    path = Path(args.file)
    if not path.is_file():
        raise UserError(f"file not found: {path}")
    print(task_source(root).load_plan(path.resolve()))
    print("Next: relay start --next")


def cmd_tools(args):
    _, policy, plugins = _setup()
    for spec in tools.REGISTRY.values():
        print(f"{tools.mode_for(spec.name, policy):5}  {spec.name:12} {spec.description}")
    print(f"\nDrivers: {', '.join(sorted(DRIVERS))}")
    if plugins:
        print(f"Plugins: {', '.join(plugins)}")


def _sessions(root):
    base = state_dir(root) / "sessions"
    if not base.is_dir():
        return []
    rows = []
    for path in sorted(base.glob("*/session.json"), key=lambda p: p.stat().st_mtime):
        data = json.loads(path.read_text(encoding="utf-8"))
        events = []
        trace = path.parent / "trace.jsonl"
        if trace.is_file():
            events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line]
        rows.append((data, events))
    return rows


def cmd_status(args):
    root = repo_root()
    rows = _sessions(root)
    if not rows:
        print("No sessions. Run: relay start")
        return
    print(f"{'SESSION':22} {'STATUS':12} {'TURNS':5}  TITLE")
    for data, _ in rows:
        print(f"{data['id']:22} {data['status']:12} {data['turn']:<5}  {data['task'].get('title', '')}")


def cmd_report(args):
    root = repo_root()
    rows = _sessions(root)
    if not rows:
        print("No sessions.")
        return
    print("| Session | Driver | Status | Turns | Tool calls | Refused or denied | Checks failed | Minutes |")
    print("|---|---|---|---|---|---|---|---|")
    done = first_try = 0
    for data, events in rows:
        calls = [e for e in events if e["event"] == "tool"]
        blocked = sum(1 for e in calls if e["status"] in ("refused", "denied"))
        failed = sum(1 for e in events if e["event"] == "check" and not e["ok"])
        minutes = round((events[-1]["t"] - events[0]["t"]) / 60) if events else 0
        if data["status"] == FINISHED:
            done += 1
            first_try += failed == 0
        print(f"| {data['id']} | {data['driver']} | {data['status']} | {data['turn']} | "
              f"{len(calls)} | {blocked} | {failed} | {minutes} |")
    print(f"\nSessions: {len(rows)}. Finished: {done}. Finished with no failed check: {first_try}.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="relay", description=__doc__)
    parser.add_argument("--version", action="version", version=f"relay {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="create .relay/policy.json").set_defaults(fn=cmd_init)

    p = sub.add_parser("start", help="start a session on a task")
    p.add_argument("task", nargs="?", help="task id (a bead id when Beads is in use)")
    p.add_argument("--next", action="store_true", help="take the next ready task")
    p.add_argument("--title", help="create a new task with this title")
    p.add_argument("--description", help="description for a new task")
    p.add_argument("--skill", help="skill to use, e.g. implement-with-tests")
    p.add_argument("--driver", help="how turns reach the model (default from policy)")
    p.add_argument("--with", dest="with_paths", action="append", metavar="PATH",
                   help="load this file or folder into the first turn (repeatable)")
    p.add_argument("--note", help="extra instructions for the model")
    p.add_argument("--no-check-gate", action="store_true",
                   help="let the model finish without a passing check (planning or docs work)")
    p.add_argument("--yes", action="store_true", help="approve tool calls that would ask")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("step", help="feed the model's reply and continue")
    p.add_argument("file", nargs="?", help="file holding the reply, or - for stdin")
    p.add_argument("--paste", action="store_true", help="read the reply from the clipboard")
    p.add_argument("--say", help="add a message from you to the next turn")
    p.add_argument("--yes", action="store_true", help="approve tool calls that would ask")
    p.add_argument("--session")
    p.set_defaults(fn=cmd_step)

    p = sub.add_parser("say", help="answer a question the model asked")
    p.add_argument("text")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--session")
    p.set_defaults(fn=cmd_say)

    p = sub.add_parser("check", help="run a named check yourself; its output goes to the model")
    p.add_argument("name", nargs="?", default="default")
    p.add_argument("--session")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("close", help="close the task after you have reviewed and merged")
    p.add_argument("reason", nargs="?")
    p.add_argument("--force", action="store_true")
    p.add_argument("--session")
    p.set_defaults(fn=cmd_close)

    p = sub.add_parser("plan", help="load a plan file into Beads")
    p.add_argument("file")
    p.set_defaults(fn=cmd_plan)

    sub.add_parser("tools", help="list tools, their policy modes, and drivers").set_defaults(fn=cmd_tools)
    sub.add_parser("status", help="list sessions").set_defaults(fn=cmd_status)
    sub.add_parser("report", help="summarize sessions from their traces").set_defaults(fn=cmd_report)

    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 1
    try:
        args.fn(args)
    except UserError as exc:
        print(f"relay: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
