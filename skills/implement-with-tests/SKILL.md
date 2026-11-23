---
name: implement-with-tests
description: Implements a code change test-first and proves it works before calling it done. Use when asked to implement a feature or task, fix a bug, write or change code, add tests, refactor, or carry out a task from a plan or ticket. Applies to any language. Covers reproducing bugs with a failing test, making small verified changes, running the project's own checks, and reporting exactly what was and was not verified.
metadata:
  version: "1.0"
  category: software-development
---

# Implement with tests

Write the change the way a careful engineer would: understand the code first, pin the expected behavior down in a test, make the smallest change that passes, and show the evidence. Generated code that merely looks plausible is the main risk of AI-assisted development, and tests that ran are the only thing that separates "written" from "working".

## Know which mode you are in

- **Execution mode**: you can read the repository and run commands. Run everything yourself. Never report a result you did not observe.
- **Chat mode**: you only have what was pasted or uploaded. Write the tests and the code, give the exact commands for the person to run, and say plainly that nothing has been executed. Ask them to paste failures back, and iterate from the real output.

The honesty rule is the same in both: "tests pass" may only be said when you saw them pass in this session.

## 1. Understand before changing

- Restate the task and its acceptance criteria in a few lines. If there are none, write them and confirm the ones that are guesses.
- Read the code you will touch and at least one neighbor that does something similar. Match its naming, structure, error handling and test style. Consistency with the codebase beats your own preference.
- Find how the project builds, tests, lints and formats (README, CONTRIBUTING, AGENTS.md or GEMINI.md, Makefile, package scripts, CI configuration). Use those commands, not ones you assume.
- Run the existing tests once before changing anything, so you know what was already failing and do not get blamed for, or waste time on, old failures.

If the task is unclear in a way that changes the design, ask before coding. If it is large or touches many files, plan it first (use the spec-to-plan skill if it is available).

## 2. Write the test first

- **Bug fix**: write a test that reproduces the bug and watch it fail for the right reason. A fix without a reproducing test is a guess.
- **New behavior**: write tests for the acceptance criteria, including at least one error case and one boundary case. Watch them fail.
- **Refactor**: make sure tests cover the current behavior before you move anything. Add characterization tests if they do not.

Good tests assert on behavior a user or caller would notice, not on implementation details. Avoid tests that only check a mock was called, or that repeat the implementation's logic to compute the expected value.

If a test cannot reasonably be written (pure configuration, generated code, UI with no harness), say so and give the manual check you will use instead.

## 3. Make the smallest change that passes

- Change only what the task needs. Leave unrelated cleanup, renames and reformatting out of the diff; note them as follow-ups. Small diffs get real reviews.
- Prefer the standard library and dependencies the project already has. Adding a dependency is a decision for the person: propose it with the reason, the license and the maintenance status, and wait.
- Handle errors where they happen. Validate input at trust boundaries. Do not swallow exceptions or add silent fallbacks to make a test pass.
- Never put secrets, tokens, credentials or real personal data in code, tests, fixtures, logs or commit messages. Use environment variables and synthetic data.
- Use only APIs you have confirmed exist in the version the project pins. Check the lockfile or manifest for the version, then check the installed source or official docs. A hallucinated method name wastes a full cycle.

## 4. Verify

Run, in this order, and fix what fails before moving on:

1. The new tests.
2. The full test suite for the affected module, then the whole suite if it is affordable.
3. Lint, format and type checks.
4. The build.
5. Any security or dependency scan the project runs in CI, if available locally.

When something fails, read the actual error and find the cause. Do not weaken or delete a test, add a skip, loosen a type, or raise a timeout to get to green unless the test itself is wrong, and say so explicitly if it is.

If you fail the same check three times, stop and report what you tried and what you learned. A clear description of a blocker is more useful than a fourth guess.

Before finishing, read your own diff from top to bottom as a reviewer would. Look for leftover debug output, commented-out code, TODOs you meant to resolve, and changes you did not intend.

## 5. Report

Close with a short, factual summary:

```
## What changed
Files and the reason for each, in one line apiece.

## Evidence
Commands run and their results (counts of tests passed/failed, lint, build).
Or: "Not executed. Run: <commands>."

## Acceptance criteria
Each criterion: met / not met / not verified, with the test that covers it.

## Not done / follow-ups
Anything skipped, assumed, or out of scope that someone should know about.

## Suggested commit message
Imperative subject under 72 characters, then why the change was made.
```

Do not commit, push, open a pull request, run migrations, or change shared environments unless the person asked for that step. Those are theirs to approve.

## Working from an ai-task context file

Some teams run this skill in a chat window with no repository access and use a
small local tool, `ai-task`, as the hands. You will recognize this when the
input starts with `# AI TASK CONTEXT` or `# AI TASK FEEDBACK`.

- The context file holds the task, the repository files, and a **Response
  format** section. Follow that format exactly: a short explanation, then one
  four-backtick code block containing complete files between
  `=== FILE: path ===` and `=== END FILE ===` markers. The tool writes each file
  exactly as sent, so never send fragments, diffs, or "unchanged" placeholders.
- You are in chat mode. Write the tests and the code together in the same
  bundle, and never claim anything was run. The person runs the check command
  named in the context and sends back a feedback file if it fails.
- On feedback, find the cause in the check output and send only the files that
  need to change. If the same check fails three times, stop and explain what you
  think is wrong instead of sending another guess.
- Files listed as omitted were withheld on purpose (size or possible secrets).
  Ask for what you need by path. Never ask for credentials or secret values.
