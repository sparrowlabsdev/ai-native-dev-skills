"""Drivers carry a turn to the model and bring the reply back.

A driver's send() returns the reply text, or None when the reply will arrive
later (a person is carrying it). The core loop does not care which.

To add a driver, subclass Driver and register it with @driver("name").
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import UserError

DRIVERS: dict = {}


def driver(name):
    def register(cls):
        cls.name = name
        DRIVERS[name] = cls
        return cls
    return register


class Driver:
    name = "base"
    #: True when the harness must put the skill text in the first turn itself.
    injects_skill = True
    #: True when a person reads the harness output and relays each turn.
    interactive = False

    def __init__(self, settings: dict, root: Path):
        self.settings = settings or {}
        self.root = root

    def send(self, session, turn_text: str, turn_file: Path):
        raise NotImplementedError


def copy_to_clipboard(text: str) -> bool:
    for cmd in (["pbcopy"], ["clip.exe"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text, text=True, check=True, timeout=10)
                return True
            except (subprocess.SubprocessError, OSError):
                continue
    return False


def read_clipboard() -> str:
    for cmd in (["pbpaste"], ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"],
                ["wl-paste"], ["xclip", "-selection", "clipboard", "-o"]):
        if shutil.which(cmd[0]):
            try:
                return subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10).stdout
            except (subprocess.SubprocessError, OSError):
                continue
    raise UserError("no clipboard tool found. Save the reply to a file and pass its path")


@driver("manual")
class ManualDriver(Driver):
    """A person pastes each turn into a chat window and brings the reply back."""

    injects_skill = False   # the person invokes the skill in the chat product
    interactive = True

    def send(self, session, turn_text, turn_file):
        rel = turn_file.relative_to(self.root)
        copied = copy_to_clipboard(turn_text)
        size_kb = len(turn_text.encode("utf-8")) // 1024
        print(f"\nTurn {session.turn} is ready: {rel} ({size_kb} KB)"
              + (", copied to the clipboard." if copied else "."))
        if session.turn == 1:
            hint = f" and invoke /{session.skill}" if session.skill else ""
            print(f"  1. Start a new chat{hint}.")
            print("  2. Paste the turn (or upload the file if it is too long to paste).")
        else:
            print("  1. Paste it into the same chat.")
        print("  3. Copy the code block from the reply, then run: relay step --paste"
              if session.turn == 1 else
              "  2. Copy the code block from the reply, then run: relay step --paste")
        return None


@driver("command")
class CommandDriver(Driver):
    """Pipe the conversation to a program and read the model's reply from stdout.

    Works with any CLI or script that wraps a model. The program is stateless,
    so it receives the whole transcript each turn.
    """

    def send(self, session, turn_text, turn_file):
        cmd = self.settings.get("cmd") or []
        if not cmd:
            raise UserError("the command driver needs drivers.command.cmd in .relay/policy.json")
        transcript = session.transcript()
        try:
            done = subprocess.run(cmd, input=transcript, text=True, capture_output=True,
                                  cwd=str(self.root), shell=isinstance(cmd, str),
                                  timeout=int(self.settings.get("timeout_seconds", 600)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UserError(f"model command failed: {exc}")
        if done.returncode != 0:
            sys.stderr.write(done.stderr or "")
            raise UserError(f"model command exited with {done.returncode}")
        return done.stdout


def make_driver(name: str, policy: dict, root: Path) -> Driver:
    if name not in DRIVERS:
        raise UserError(f"unknown driver '{name}'. Available: {', '.join(sorted(DRIVERS))}")
    return DRIVERS[name](policy.get("drivers", {}).get(name, {}), root)
