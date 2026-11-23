"""The text protocol between model and harness.

It is plain text on purpose: it survives copy and paste through a chat window,
and file contents need no escaping.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

CALL = re.compile(r"^=== CALL (.+?) ===\s*$")
END = re.compile(r"^=== END ===\s*$")


@dataclass
class Call:
    name: str
    args: dict = field(default_factory=dict)
    body: str = ""
    error: str = ""

    def label(self) -> str:
        args = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in self.args.items())
        return f"{self.name} {args}".strip()


def parse_calls(text: str, body_tools: set) -> list:
    """Extract tool calls from a model reply. Text outside calls is ignored."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    calls, i = [], 0
    while i < len(lines):
        match = CALL.match(lines[i])
        i += 1
        if not match:
            continue
        try:
            tokens = shlex.split(match.group(1))
        except ValueError as exc:
            calls.append(Call(name="?", error=f"could not parse call header: {exc}"))
            continue
        if not tokens:
            continue
        call = Call(name=tokens[0])
        for token in tokens[1:]:
            if "=" not in token:
                call.error = f"argument '{token}' must be written as name=value"
                break
            key, value = token.split("=", 1)
            call.args[key] = value
        if call.name in body_tools:
            body, closed = [], False
            while i < len(lines):
                if END.match(lines[i]):
                    closed = True
                    i += 1
                    break
                body.append(lines[i])
                i += 1
            if not closed:
                call.error = call.error or "missing '=== END ===' after the body"
            call.body = "\n".join(body) + ("\n" if body else "")
        calls.append(call)
    return calls


def render_result(index: int, call: Call, status: str, output: str) -> str:
    output = output.rstrip("\n")
    return (
        f"=== RESULT {index}: {call.label()} [{status}] ===\n"
        f"{output}\n"
        f"=== END RESULT ===\n"
    )


def protocol_help(tool_lines: str) -> str:
    return f"""## Protocol

You cannot touch the repository directly. You act by requesting tools. A
harness runs the tools it is permitted to run and sends you the results in the
next turn. A person may be carrying each turn by hand, so every round trip is
expensive: ask for everything you need in one reply, and when you know what to
write, write the files and request the check in the same reply.

Reply with a short explanation, then ONE code block fenced with four backticks
that contains only tool calls, in this form:

=== CALL read_file path=src/app.py ===
=== CALL write_file path=src/app.py ===
<the complete new content of the file>
=== END ===
=== CALL run_check name=default ===

Rules:
- A call is one header line. Arguments are name=value; quote values that
  contain spaces.
- Tools marked "body" take everything up to a line reading === END === as
  their input. Tools without a body have no END line.
- write_file replaces the whole file with exactly what you send. Never send
  fragments, diffs or "unchanged" placeholders.
- Calls run in order. If one fails, the later ones still run.
- You never run anything yourself and nothing has been run unless a RESULT
  says so. Do not claim a check passed without seeing its result.
- A result of [denied] or [refused] is final for that request. Do not retry
  it; adapt, or use the ask tool.
- Never ask for credentials, tokens or secret values.
- When the work is complete and a check has passed since your last change,
  call finish with a summary.

## Tools

{tool_lines}"""


REMINDER = (
    "Reply with a short explanation and one four-backtick code block of "
    "=== CALL ... === lines, as before. Batch your requests."
)
