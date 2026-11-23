# relay: the harness

`relay` runs a model against a repository through a small agent loop. It is
built so the parts that differ between environments are separate, and the loop
itself never changes:

```
            +-----------+   turn    +--------+          +-------+
  task ---> | core loop | --------> | driver | -------> | model |
 (Beads)    |           | <-------- |        | <------- |       |
            +-----------+   reply   +--------+          +-------+
              |   ^
   tool calls |   | results          policy: which tools, which paths, which checks
              v   |                  trace:  every turn, call, approval and check
            +-------+
            | tools |
            +-------+
```

| Part | What it is | Where | How to extend it |
|---|---|---|---|
| Core loop | Send a turn, parse tool calls, apply policy, run tools, return results | `relay/session.py` | Rarely needed |
| Drivers | How a turn reaches the model | `relay/drivers.py` | Subclass `Driver`, register with `@driver("name")` |
| Tools | What the model may ask for | `relay/tools.py` | `@tool(...)` function; project tools in `.relay/tools/*.py` |
| Policy | What is allowed | `.relay/policy.json` | Edit the file |
| Tasks | Where work comes from | `relay/tasks.py` | Beads by default; add a class with the same methods |
| Skills | How to do a kind of work | `skills/*/SKILL.md` | Add a folder |
| Trace | The record | `.relay/sessions/<id>/trace.jsonl` | One JSON object per event |

Python 3.9 or later, standard library only. Run it from a clone with
`bin/relay`, or `python3 -m relay` with the repository on `PYTHONPATH`.

## Drivers

- **manual** (default): for a chat model in a browser and nothing else. The
  harness writes each turn to a file and the clipboard; you paste it into the
  chat, copy the reply's code block, and run `relay step --paste`. You invoke
  the skill in the chat product yourself.
- **command**: pipes the transcript to any program and reads the reply from
  its output, so the loop runs unattended. Point `drivers.command.cmd` at a
  model CLI or a small script that calls an API. The harness adds the skill
  text to the first turn.

Moving from the manual driver to a real model connection changes one line of
policy. Tools, policy, skills, tasks and the trace format stay the same, so
numbers from a manual pilot are comparable with later runs.

## Using it

```bash
relay init                                   # writes .relay/policy.json
# set "checks": {"default": "<command that proves a change works>"}

relay start --next --skill implement-with-tests      # next ready bead
relay start bd-a1b2 --skill implement-with-tests     # or a specific one
relay start --title "Add a health endpoint"          # or a new task

relay step --paste          # manual driver: feed the reply, get the next turn
relay step --paste --say "use the existing logger"   # add a message from you
relay say "us-gov-west-1"   # answer a question the model asked with the ask tool
relay check build           # run a check yourself; output goes to the model next turn
relay close                 # close the task after you have reviewed and merged

relay status                # sessions
relay report                # turns, tool calls, refusals, failed checks, minutes
relay tools                 # tools with their policy modes, and drivers
relay plan plans/x.plan.json    # load a plan file into Beads
```

Tasks are [Beads](https://github.com/steveyegge/beads) issues when `bd` is
installed and the repository has `.beads/`. Otherwise they are kept in
`.relay/tasks.json`. `bd metrics off` turns off Beads' anonymous usage metrics.

## Tools and policy

Built-in tools: `list_files`, `read_file`, `search`, `git_diff`, `write_file`,
`delete_file`, `run_check`, `ask`, `finish`.

Each tool has a mode in policy:

- `auto`: runs without asking.
- `ask`: you approve each call at the prompt (or pass `--yes`).
- `deny`: never runs, and is not shown to the model.

Tools not listed in policy, including any you add, default to `ask`.

```json
{
  "checks": { "default": "make test", "build": "make image" },
  "tools": { "run_check": "ask", "delete_file": "deny" },
  "allow_name_globs": ["example.pkrvars.hcl"],
  "deny_path_globs": ["infra/prod/*"],
  "default_driver": "manual"
}
```

## What it guarantees

- **The model never supplies a command.** `run_check` takes the name of a check
  from your policy file. Because a check executes project files the model may
  have changed, `run_check` defaults to `ask`.
- **Writes stay in the repository.** Absolute paths, `..`, symlinks, and
  anything under `.git`, `.relay` or `.beads` are refused. The policy file and
  the plugin folder are therefore out of the model's reach.
- **Secrets are withheld, as a guard and not a guarantee.** Files with
  secret-looking names (`.env`, `*.pem`, `*.tfvars`, `*.pkrvars.hcl`, ...) or
  key-like content, binaries and oversized files are never shown. You still
  decide what is appropriate to send to your chat tenant: read turn 1 before
  pasting it.
- **Model changes are separate from yours.** Changes go on `relay/<task>`, one
  commit per turn titled "model output (unreviewed)". It refuses to start
  writing over uncommitted changes, stages only the files the model wrote, and
  never merges or pushes.
- **Finishing is gated.** If the session changed files, `finish` is refused
  until a check has passed since the last change. Start a session with
  `--no-check-gate` for planning or documentation work that has no check.

## The trace

`trace.jsonl` holds one event per line: `session_start`, `turn_out`, `turn_in`,
`tool` (name, arguments, status, duration), `approval`, `check`, `commit`,
`question`, `session_end`. The turns themselves are kept beside it in `turns/`.
Commit `.relay/` if you want that record in the repository.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests cover the protocol parser, the path and secret guards, a full run
with the command driver against a scripted model, and a manual session resumed
across separate loads.
