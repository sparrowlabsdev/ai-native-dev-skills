# The manual agent loop

For teams that have a chat model in a browser but no coding agent yet. The
model does the thinking in the chat window. `bin/ai-task` does what an agent's
tools would do: gather context, write files, run checks, keep a record. A
person carries files between the two and approves every step.

```
  bd ready ──> ai-task next ──> ai-task pack ──> upload context.md + /skill
                                                         │
     ai-task done <── PASS ── ai-task check <── ai-task apply --paste
                                 │
                               FAIL ──> ai-task feedback --copy ──> same chat
```

## Setup (once per project)

1. Put `bin/ai-task` on your PATH, or call it by its full path. It needs bash
   and git only; on Windows use Git Bash.
2. Optional but recommended: install [Beads](https://github.com/steveyegge/beads)
   (`bd`) and run `bd init` in the project. Tasks then become beads, with
   dependencies and a ready queue. `bd init --stealth` keeps tracker files out
   of the repository. `bd metrics off` turns off its anonymous usage metrics.
   Without `bd`, `ai-task new` still works and gives tasks local ids.
3. In the project: `ai-task init`, then set `CHECK_CMD` in `.ai/config` to the
   command that proves a change works.
4. Make sure the repository has at least one commit.

## Plan

```bash
ai-task new "Plan: <feature>" -t spike     # a task to hold the planning round
# edit .ai/tasks/<id>/task.md with what you want built
ai-task pack
# upload context.md, invoke /spec-to-plan, ask for the plan as beads
ai-task apply --paste                      # writes docs/specs/... and plans/....plan.json
# read both files, edit them if needed, then:
ai-task plan plans/<slug>.plan.json        # creates the beads and their dependencies
ai-task done --force "Plan loaded"
```

## Build, one bead at a time

```bash
ai-task next              # claims the first ready bead
ai-task pack              # writes .ai/tasks/<id>/context.md
```

Read `context.md` before uploading it. Upload it to the chat, invoke
`/implement-with-tests`, and copy the code block from the reply.

```bash
ai-task apply --paste     # writes the files on branch ai/<id> and commits them
git show                  # review what the model wrote
ai-task check             # runs CHECK_CMD, saves check.log
```

If the check fails: `ai-task feedback --copy`, paste into the same chat, copy
the new code block, and `ai-task apply --paste` again.

If it passes: review the branch, merge it yourself, switch back to your main
branch, then `ai-task done`. Run `ai-task next` for the next bead.

To get a second opinion before merging: `ai-task pack --review`, upload with
`/pr-review`.

## What the tool will and will not do

- **It never runs anything the model wrote.** Commands suggested in a reply are
  for you to read. The only command it runs is your own `CHECK_CMD`, or one you
  type after `ai-task check --`. Review the commit before running the check,
  because the check executes project files the model may have changed.
- **It writes only inside the repository.** Paths that are absolute, contain
  `..`, pass through a symlink, or point into `.git`, `.ai` or `.beads` are
  rejected, and nothing is written if any path in the reply is rejected.
- **It keeps model changes separate from yours.** Each round is its own commit
  on `ai/<id>`, titled "model output (unreviewed)", and it refuses to apply over
  uncommitted changes. Only the files named in the reply are staged. Undo a
  round with `git reset --hard HEAD~1`. It never merges or pushes.
- **It filters context, as a guard and not a guarantee.** Files ignored by git,
  binaries, large files, names that look like secrets (`.env`, `*.pem`,
  `*.tfvars`, `*.pkrvars.hcl`, ...) and files containing key-like strings are
  left out and listed as omitted. Tune this with `PACK_EXCLUDE` and
  `PACK_ALLOW`. You are still responsible for what you upload: read
  `context.md` first, and upload only data your chat tenant is approved for.

## The record

Each task folder under `.ai/tasks/<id>/` holds:

| File | Contents |
|---|---|
| `task.md` | Your notes for the model |
| `context.md` | The last bundle uploaded (not committed by default) |
| `response-NN.txt` | Each reply, exactly as applied |
| `check.log`, `feedback.md` | The last check output and what was sent back |
| `events.tsv` | Timestamped log: new, claim, pack, apply, check-pass/fail, done |

`ai-task report` turns the event logs into a table: rounds per task, failed
checks, whether it passed, and minutes to the first pass. Commit `.ai/` if you
want that record in the repository.
