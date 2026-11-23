"""Tests for relay. Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from relay import guard, protocol, tools  # noqa: E402
from relay.config import DEFAULT_POLICY, load_policy  # noqa: E402
from relay.guard import Refused  # noqa: E402
from relay.session import FINISHED, Session  # noqa: E402
from relay.tasks import LocalTasks  # noqa: E402


def git(root, *args):
    subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)


def make_repo(tmp, checks=None, driver="manual"):
    root = Path(tmp).resolve()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "Tester")
    (root / "README.md").write_text("# demo\n")
    (root / ".env").write_text("TOKEN=abc\n")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "init")
    (root / ".relay").mkdir()
    policy = {"checks": checks or {}, "default_driver": driver, "tools": {"run_check": "auto"},
              "drivers": {"command": {"cmd": [sys.executable, str(REPO / "tests" / "fake_model.py")]}}}
    (root / ".relay" / "policy.json").write_text(json.dumps(policy))
    return root


class ProtocolTests(unittest.TestCase):
    def test_parses_calls_bodies_and_quotes(self):
        text = ("chat\n````\n=== CALL read_file path=a.py ===\n"
                "=== CALL write_file path=\"docs/my file.md\" ===\nline 1\n```py\nx\n```\n=== END ===\n"
                "=== CALL run_check ===\n````\n")
        calls = protocol.parse_calls(text, {"write_file"})
        self.assertEqual([c.name for c in calls], ["read_file", "write_file", "run_check"])
        self.assertEqual(calls[1].args["path"], "docs/my file.md")
        self.assertEqual(calls[1].body, "line 1\n```py\nx\n```\n")
        self.assertFalse(any(c.error for c in calls))

    def test_reports_missing_end_and_bad_args(self):
        calls = protocol.parse_calls("=== CALL write_file path=a ===\nbody\n", {"write_file"})
        self.assertIn("END", calls[0].error)
        calls = protocol.parse_calls("=== CALL read_file a.py ===\n", set())
        self.assertIn("name=value", calls[0].error)

    def test_handles_crlf_and_ignores_prose(self):
        calls = protocol.parse_calls("hi\r\n=== CALL list_files ===\r\nbye\r\n", set())
        self.assertEqual(len(calls), 1)


class GuardTests(unittest.TestCase):
    def test_rejects_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            root = make_repo(tmp)
            os.symlink(other, root / "link")
            for bad in ["../x", "/etc/passwd", "a/../../x", ".git/config", ".relay/policy.json",
                        ".beads/x", "C:\\x", "link/x", "link", ""]:
                with self.assertRaises(Refused, msg=bad):
                    guard.safe_rel(root, bad, DEFAULT_POLICY)
            self.assertEqual(guard.safe_rel(root, "src/new/a.py", DEFAULT_POLICY), "src/new/a.py")

    def test_withholds_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "key.txt").write_text("-----BEGIN RSA PRIVATE KEY-----\n")
            (root / "prod.pkrvars.hcl").write_text("x=1\n")
            self.assertIn("secret", guard.unreadable_reason(root, ".env", DEFAULT_POLICY))
            self.assertIn("credential", guard.unreadable_reason(root, "key.txt", DEFAULT_POLICY))
            self.assertIsNotNone(guard.unreadable_reason(root, "prod.pkrvars.hcl", DEFAULT_POLICY))
            allow = dict(DEFAULT_POLICY, allow_name_globs=["prod.pkrvars.hcl"])
            self.assertIsNone(guard.unreadable_reason(root, "prod.pkrvars.hcl", allow))
            self.assertIsNone(guard.unreadable_reason(root, "README.md", DEFAULT_POLICY))


class LoopTests(unittest.TestCase):
    def start(self, root, driver):
        policy = load_policy(root)
        task = LocalTasks(root).create("Add hello.txt")
        session = Session.create(root, policy, task, "", driver)
        return policy, session

    def test_command_driver_runs_to_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, checks={"default": "grep -q hello hello.txt"}, driver="command")
            policy, session = self.start(root, "command")
            session.run(session.first_turn())
            self.assertEqual(session.d["status"], FINISHED)
            self.assertEqual((root / "hello.txt").read_text(), "hello\n")
            self.assertFalse((root.parent / "outside.txt").exists())
            events = [json.loads(l) for l in (session.dir / "trace.jsonl").read_text().splitlines()]
            by_name = {}
            for e in events:
                if e["event"] == "tool":
                    by_name.setdefault(e["name"], []).append(e["status"])
            # turn 1: secret read and escaping write refused; early finish refused
            self.assertIn("refused", by_name["read_file"])
            self.assertEqual(by_name["write_file"].count("refused"), 1)
            self.assertEqual(by_name["finish"], ["refused", "ok"])
            self.assertEqual([e["ok"] for e in events if e["event"] == "check"], [False, True])
            branch = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=str(root),
                                    capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, f"relay/{session.d['task']['id']}")
            log = subprocess.run(["git", "log", "--format=%s"], cwd=str(root),
                                 capture_output=True, text=True).stdout
            self.assertEqual(log.count("model output (unreviewed)"), 2)
            status = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                                    capture_output=True, text=True).stdout
            self.assertIn("?? .env", status)          # untracked files are never swept into commits

    def test_manual_driver_waits_and_resumes_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, checks={"default": "test -f a.txt"})
            policy, session = self.start(root, "manual")
            session.run(session.first_turn())
            self.assertEqual(session.d["status"], "waiting")
            first = (session.dir / "turns" / "001-out.md").read_text()
            self.assertIn("=== CALL", first)
            self.assertIn("README.md", first)
            self.assertNotIn("TOKEN=abc", first)

            resumed = Session.load(root, policy)        # a new process would do this
            resumed.feed("=== CALL write_file path=a.txt ===\nx\n=== END ===\n=== CALL run_check ===\n")
            self.assertEqual(resumed.d["status"], "waiting")
            second = (resumed.dir / "turns" / "002-out.md").read_text()
            self.assertIn("CHECK PASSED", second)

            final = Session.load(root, policy)
            final.feed("=== CALL finish ===\ndone\n=== END ===\n")
            self.assertEqual(final.d["status"], FINISHED)

    def test_ask_mode_denies_without_a_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, checks={"default": "true"})
            pol = json.loads((root / ".relay" / "policy.json").read_text())
            pol["tools"]["run_check"] = "ask"
            (root / ".relay" / "policy.json").write_text(json.dumps(pol))
            policy, session = self.start(root, "manual")
            session.run(session.first_turn())
            stdin, sys.stdin = sys.stdin, open(os.devnull)
            try:
                session.feed("=== CALL run_check ===\n")
            finally:
                sys.stdin.close()
                sys.stdin = stdin
            self.assertIn("[denied]", (session.dir / "turns" / "002-out.md").read_text())

    def test_refuses_to_apply_over_uncommitted_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            policy, session = self.start(root, "manual")
            session.run(session.first_turn())
            (root / "README.md").write_text("edited by a person\n")
            from relay.config import UserError
            with self.assertRaises(UserError):
                session.feed("=== CALL write_file path=b.txt ===\nx\n=== END ===\n")
            self.assertFalse((root / "b.txt").exists())

    def test_plugin_tools_load_and_default_to_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / ".relay" / "tools").mkdir()
            (root / ".relay" / "tools" / "echo.py").write_text(
                "from relay.tools import tool\n"
                "@tool('echo_test', 'Echo the body.', body='text')\n"
                "def echo(ctx, args, body):\n    return body\n")
            self.assertEqual(tools.load_plugins(root), ["echo.py"])
            self.assertIn("echo_test", tools.REGISTRY)
            self.assertEqual(tools.mode_for("echo_test", load_policy(root)), "ask")
            del tools.REGISTRY["echo_test"]


if __name__ == "__main__":
    unittest.main()
