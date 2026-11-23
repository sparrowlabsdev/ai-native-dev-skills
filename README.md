# AI-native development skills

Agent skills for AI-native software development, written in the open
[Agent Skills](https://agentskills.io) format (`SKILL.md`). They are generic:
no assumptions about language, stack, or organization.

| Skill | Use it for |
|---|---|
| [`spec-to-plan`](skills/spec-to-plan/SKILL.md) | Turning a ticket or idea into a one-page spec and an ordered, agent-ready task plan |
| [`implement-with-tests`](skills/implement-with-tests/SKILL.md) | Test-first implementation with verification before "done" |
| [`pr-review`](skills/pr-review/SKILL.md) | Prioritized review of a PR or diff: correctness, security, tests, AI-generated code tells |
| [`vuln-remediation`](skills/vuln-remediation/SKILL.md) | Triage and fix of CVE and scanner findings, with justification for anything left open |

Each skill works in two modes. With repository and terminal access (a coding
agent) it reads the code and runs the checks itself. In a chat-only assistant
it works from pasted material and states that nothing was executed.

## Layout

```
skills/<name>/SKILL.md      one folder per skill; folder name = skill name
relay/                      the harness: core loop, drivers, tools, policy, trace
bin/relay                   run the harness from a clone
docs/harness.md             how the harness works and how to extend it
docs/trial-packer-ami.md    a first project to try it on
tests/                      python3 -m unittest discover -s tests
scripts/validate.py         checks skill names, descriptions and size limits
scripts/package.sh          builds dist/<name>.zip for upload
```

## The harness

`relay` is a small agent loop in Python (standard library only). The model
requests tools; the harness applies policy, runs them against the repository,
and returns the results. How a turn reaches the model is a pluggable driver:

- **manual**: you paste each turn into a chat window and bring the reply back.
  This is the one to use when all you have is a model in a browser.
- **command**: any CLI or script that wraps a model, so the loop runs on its
  own.

Tools, policy, skills, tasks ([Beads](https://github.com/steveyegge/beads)) and
the trace are the same for every driver, so work done by hand carries over when
a direct model connection becomes available.

```bash
relay init
relay start --next --skill implement-with-tests
relay step --paste          # repeat until the model finishes
relay close
```

See [docs/harness.md](docs/harness.md), and
[docs/trial-packer-ami.md](docs/trial-packer-ami.md) for a worked first project.

## Use in the Gemini Enterprise web app

Skills must be turned on by a Gemini Enterprise administrator.

```bash
./scripts/package.sh
```

Then in the web app: **Skills** > add > upload, and choose a ZIP from `dist/`.
Upload one ZIP per skill. Invoke with `/skill-name`, or let it trigger from its
description.

Notes:

- Skills are not available to custom agents, and a skill and an agent cannot be
  invoked in the same prompt.
- Each skill here is a single `SKILL.md`, which is what works best with Canvas.

## Use in Gemini CLI

From a clone, link the whole set so edits take effect without reinstalling:

```bash
gemini skills link ./skills
```

Or install copies, for your user or for one project:

```bash
gemini skills install ./skills/pr-review
gemini skills install ./skills/pr-review --scope workspace
```

Check what is loaded with `/skills list` inside a session. Command names and
flags have changed between Gemini CLI releases; if one fails, run
`gemini skills --help`.

Because the format is an open standard, the same folders can be copied into
other agents' skills directories.

## Changing or adding a skill

1. Edit `skills/<name>/SKILL.md`, or add a new folder with its own `SKILL.md`.
2. Keep the `description` on one line. It decides when the skill triggers, so
   say what the skill does and the phrases that should invoke it.
3. Run `python3 scripts/validate.py`.
4. Try it on a real ticket, diff or scan report before sharing it.

Limits enforced by the validator (Gemini Enterprise upload rules): `name` up to
64 characters of lowercase letters, numbers and single hyphens, matching the
folder; `description` up to 1,024 characters; body up to 500,000 characters.
