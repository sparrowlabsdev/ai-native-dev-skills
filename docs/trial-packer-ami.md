# Trial: a Packer build for an AMI

A first project for the manual loop. It is a good fit: the work is a handful of
small files, and `packer validate` gives a fast, objective check.

## 1. Set up

```bash
mkdir ami-build && cd ami-build && git init -b main
echo "# AMI build" > README.md && git add README.md && git commit -m "Initial commit"
bd init                      # optional; add --stealth to keep tracker files uncommitted
ai-task init
```

In `.ai/config`:

```bash
CHECK_CMD="packer init . && packer fmt -check -recursive . && packer validate ."
PACK_ALLOW="example.pkrvars.hcl"
```

`packer init` downloads the Amazon plugin, so it needs network access to the
plugin source. If `packer validate` asks for AWS credentials in your setup, use
`packer validate -syntax-only .` for the loop and run the full validate where
credentials are available.

## 2. Write down the decisions

```bash
ai-task new "Plan: Packer build for a hardened AMI" -t spike
```

Fill in `task.md`. The model cannot guess these, and each one changes the
template:

- Base image: OS and version, and how the source AMI is selected (owner and
  name filter, or a fixed id).
- AWS partition and region, and whether the build runs in a specific VPC and
  subnet.
- Instance type and architecture.
- How Packer connects: SSH or Session Manager, public or private address.
- Provisioning: shell scripts, Ansible, or both; which hardening baseline, if
  any; what gets installed.
- Encryption: encrypted volumes, and which KMS key.
- Output: AMI naming pattern, tags, accounts or regions to share or copy to.
- Variables: what must be configurable per environment, and what must never be
  in the repository.
- Packer version and plugin version constraints.
- Where the build will run later (a laptop, a pipeline).

## 3. Plan

```bash
ai-task pack
```

Upload `context.md`, invoke `/spec-to-plan`, and ask for the plan as beads.
Answer its questions. Then:

```bash
ai-task apply --paste
# review docs/specs/*.md and plans/*.plan.json
ai-task plan plans/<slug>.plan.json
ai-task done --force "Plan loaded"
git checkout main && git merge ai/<id>
bd ready
```

A reasonable plan has four to six beads, for example: template skeleton and
variables, source AMI selection, provisioning scripts, encryption and tagging,
an example variables file and README, a pipeline job.

## 4. Build each bead

Follow "Build, one bead at a time" in [manual-loop.md](manual-loop.md), using
`/implement-with-tests`.

## 5. The real build

`packer validate` proves the template is well formed. Only a real build proves
the AMI. When credentials are available, record that run too:

```bash
ai-task check -- "packer build -var-file=<your vars file> ."
```

If it fails, `ai-task feedback --copy` sends the build output back to the chat
like any other failed check. Read the log before pasting it and remove account
ids or anything else you would not share.

## 6. What to measure

`ai-task report` gives rounds per bead and time to first pass. Add your own
notes on how many minutes went to copying between the browser and the terminal,
and which failures a tool with direct repository access would have caught
without a round trip. Those are the numbers that make the case for a coding
agent.
