---
name: spec-to-plan
description: Turns a ticket, feature idea, bug report or rough request into a short engineering spec and an ordered task plan that a coding agent or developer can execute one task at a time. Use when asked to write a spec, design doc, technical plan, acceptance criteria, or task breakdown, to "plan this feature", "break this down", "scope this ticket", or before starting any change that touches more than one file or has unclear requirements.
metadata:
  version: "1.0"
  category: software-development
---

# Spec to plan

Produce two things from a request: a spec a human can approve in five minutes, and a task plan where each task is small enough for an agent to finish and verify in one sitting. Most failed agent-written changes trace back to a vague request, so the value of this skill is in what gets pinned down before any code is written.

## Work from evidence

Find out what you can see before you write anything.

- **With repository access** (coding agent, terminal, or a connected source repository): read the code the change will touch. Find the entry points, the existing patterns for similar features, the test layout and how tests are run, and any contributor docs (README, CONTRIBUTING, AGENTS.md, GEMINI.md, architecture notes). Cite real file paths in the plan.
- **Without repository access** (chat only): work from what was pasted or uploaded. Ask for the two or three things that matter most, such as the relevant files, the data model, or an example of a similar existing feature. Mark every statement about the codebase that you could not check as an assumption.

Never invent file names, function names, endpoints or library APIs. A plan built on a guessed structure sends the implementer in the wrong direction with confidence.

## Clarify only what changes the design

Ask questions when the answer would change the approach, the data model, or the scope. Ask them all at once, at most five, each with your proposed default so the person can answer "defaults are fine". For everything else, choose the conventional option and record it under Assumptions.

Questions that are usually worth asking:

- Who uses this and what do they do today instead?
- What is explicitly out of scope?
- Are there existing users, data or integrations that must keep working unchanged?
- What does failure look like (bad input, dependency down, partial completion) and what should happen?
- Are there limits that matter: response time, volume, data sensitivity, access roles?

## Write the spec

Keep it to about one page. Use this structure:

```
# <Feature name>

## Problem
Two or three sentences: who has the problem, what happens today, why it matters.

## Outcome
What is true when this is done, stated from the user's point of view.

## Scope
In: ...
Out: ...

## Behavior
Numbered acceptance criteria. Each one is observable and testable:
"Given <state>, when <action>, then <result>."
Include the error and edge cases, not only the happy path.

## Design
The approach in a few paragraphs: components touched, data changes,
interfaces added or changed (with signatures or request/response shapes),
and the alternative you rejected and why.

## Risks and assumptions
What could go wrong, what you assumed, what you could not verify.

## Verification
How someone will prove it works: tests to add, commands to run,
manual checks.
```

Acceptance criteria are the contract. If a criterion cannot be checked by a test or a specific manual step, rewrite it until it can.

## Write the task plan

Break the work into tasks that each leave the codebase working. For each task:

```
### Task N: <imperative title>
Goal: one sentence.
Files: paths to create or change (or "unknown: needs repo access").
Steps: the concrete changes, in order.
Tests: the tests to write or update, and what they assert.
Done when: the command to run and the result that proves it.
Depends on: task numbers, or "none".
Covers: acceptance criteria numbers.
```

Guidelines for good tasks:

- **Small.** Aim for a change one person could review in ten minutes. If a task has "and" in its title, split it.
- **Vertical before horizontal.** Prefer a thin end-to-end slice first (one path working through every layer), then widen. It surfaces integration problems on task one instead of task nine.
- **Self-contained.** An agent picking up task 4 cold should not need the conversation that produced the plan. Put the needed context in the task.
- **Verifiable.** Every task ends with a command and an expected result. "Looks right" is not a done condition.
- **Ordered by risk.** Put the uncertain part early: the unfamiliar library, the schema change, the performance question.
- **Marked for parallelism.** Note which tasks can run at the same time because they touch different files.

Finish with a traceability check: every acceptance criterion is covered by at least one task, and every task covers at least one criterion. List any gaps instead of hiding them.

## Hand-off

End by stating what needs a human decision before work starts (open questions, risky assumptions, anything that changes data or public interfaces). If asked to proceed, hand tasks to implementation one at a time, in order.

Do not start implementing as part of this skill. The spec is cheap to change now and expensive to change after code exists, so give the person the chance to correct it.

## Emitting the plan as beads

When asked for beads, a plan file, or "a plan I can load", or when the input is
an `# AI TASK CONTEXT` file, deliver the plan in a form the Beads issue tracker
(`bd`) can load, so each task becomes a tracked issue with its dependencies.

Produce two files:

1. `docs/specs/<slug>.md`: the spec, as written above.
2. `plans/<slug>.plan.json`: the task plan, in this shape:

```json
{
  "nodes": [
    {
      "key": "t1",
      "title": "Imperative title under 70 characters",
      "type": "task",
      "priority": 1,
      "description": "Goal, files, steps and tests for this task. Self-contained.",
      "acceptance_criteria": "The command to run and the result that proves it."
    }
  ],
  "edges": [
    { "from_key": "t2", "to_key": "t1", "type": "blocks" }
  ]
}
```

- An edge means `from_key` cannot start until `to_key` is done.
- `priority` runs from 0 (highest) to 4. Use it to put risky work first.
- `type` is one of task, bug, feature, chore, spike. Use a spike for a question
  that must be answered before the design is safe.
- Each description must stand alone: the person or model picking up the task
  sees that bead and the repository, not this conversation.
- The file must be valid JSON. Escape newlines inside strings as `\n`.

If the context file has a Response format section, send both files in that
format. Otherwise give each file in its own code block. The person loads the
plan with `ai-task plan plans/<slug>.plan.json` after reviewing it.
