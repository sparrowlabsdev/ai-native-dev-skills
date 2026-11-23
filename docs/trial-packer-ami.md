# Trial: a Packer build for an AMI

A first project for the harness with the manual driver. It is a good fit: the
work is a handful of small files, and `packer validate` gives a fast, objective
check.

## 1. Set up

```bash
mkdir ami-build && cd ami-build && git init -b main
echo "# AMI build" > README.md && git add README.md && git commit -m "Initial commit"
bd init                      # optional; add --stealth to keep tracker files uncommitted
relay init
```

In `.relay/policy.json`:

```json
{
  "checks": {
    "default": "packer init . && packer fmt -check -recursive . && packer validate .",
    "build": "packer build -var-file=dev.pkrvars.hcl ."
  },
  "allow_name_globs": ["example.pkrvars.hcl"]
}
```

`packer init` downloads the Amazon plugin, so it needs network access to the
plugin source. If `packer validate` asks for AWS credentials in your setup, use
`packer validate -syntax-only .` for `default`.

## 2. Plan

Write the decisions down first. The model cannot guess these, and each one
changes the template:

- Base image: OS and version, and how the source AMI is selected.
- AWS partition and region; a specific VPC and subnet, if any.
- Instance type and architecture.
- How Packer connects: SSH or Session Manager, public or private address.
- Provisioning: shell scripts, Ansible, or both; hardening baseline, if any.
- Encryption: encrypted volumes, and which KMS key.
- Output: AMI naming pattern, tags, accounts or regions to share or copy to.
- Variables: what is configurable per environment, and what must never be in
  the repository.
- Packer and plugin version constraints.

```bash
relay start --title "Plan: Packer build for a hardened AMI" \
  --skill spec-to-plan --no-check-gate \
  --note "<your decisions, or the path of a notes file you added to the repo>"
```

`--no-check-gate` lets this session finish without `packer validate` passing,
since planning produces documents and no template yet.

Paste the turn into a new chat with `/spec-to-plan`, ask for the plan as beads,
and carry replies back with `relay step --paste`. If the model needs a
decision it will ask; answer with `relay say "..."`. When it finishes:

```bash
# review docs/specs/*.md and plans/*.plan.json on the relay/<id> branch
git checkout main && git merge relay/<id>
relay plan plans/<slug>.plan.json
relay close
bd ready
```

A reasonable plan has four to six beads: template skeleton and variables,
source AMI selection, provisioning scripts, encryption and tagging, an example
variables file and README, a pipeline job.

## 3. Build each bead

```bash
relay start --next --skill implement-with-tests
relay step --paste        # repeat until the model calls finish
git diff main...relay/<id>    # review
git checkout main && git merge relay/<id>
relay close
```

## 4. The real build

`packer validate` proves the template is well formed. Only a real build proves
the AMI. When credentials are available, run it yourself inside a session:

```bash
relay check build
```

The output is recorded and sent to the model with the next turn, so a failed
build is fixed the same way as a failed validate. Read the output first and
remove account ids or anything else you would not share.

## 5. What to measure

`relay report` gives, per session: turns, tool calls, refused or denied calls,
failed checks and elapsed minutes. Add your own note of how long the pasting
took. Turns multiplied by the minutes each paste costs is the overhead that a
direct model connection, the `command` driver or a full coding agent, removes.
