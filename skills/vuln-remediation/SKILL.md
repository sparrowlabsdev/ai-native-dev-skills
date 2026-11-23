---
name: vuln-remediation
description: Triages and fixes security vulnerabilities in dependencies, container images and code. Use when given a CVE or advisory ID, scanner output (for example from Trivy, Grype, Snyk, Dependabot, npm audit, pip-audit, OWASP Dependency-Check, or a SAST tool), a failed security gate, or when asked to patch, upgrade or remediate a vulnerable dependency, check whether a CVE affects a project, prioritize a list of findings, or write a risk justification for a finding that cannot be fixed yet.
metadata:
  version: "1.0"
  category: software-development
---

# Vulnerability remediation

Take a finding from "the scanner flagged it" to "fixed and verified" or "documented with a reason", with the smallest safe change. Scanner output is a list of leads, and the work is deciding which ones are real for this system and fixing those without breaking it.

## Start from facts

- **With repository access**: read the manifests and lockfiles, the container definitions, and the scan report. Run the project's scanner yourself if it is available so you have a baseline to compare against after the fix.
- **Chat only**: ask for the scanner output, the relevant manifest and lockfile, and the base image reference. Give exact commands for the person to run and work from the results they paste back.

For each advisory, use the details given to you or look them up in an authoritative source (the vendor or project advisory, the National Vulnerability Database, the GitHub Advisory Database, OSV, CISA's Known Exploited Vulnerabilities catalog). Do not state affected version ranges, fixed versions or severity from memory. These details are precise, they change, and a wrong fixed-version number produces an upgrade that fixes nothing. If you cannot look something up, say what needs checking and where.

## 1. Triage each finding

Answer these in order and record the answers:

1. **Is it really present?** Confirm the package and the exact resolved version from the lockfile or image, not the manifest range. Note whether it is a direct or transitive dependency and what pulls it in.
2. **Is the version in the affected range?** Scanners match on names and versions and produce false positives, especially for OS packages with vendor-backported fixes and for look-alike package names.
3. **Is the vulnerable code reachable?** Is the affected function, feature or configuration used? Is the component in the runtime artifact or only in build and test tooling? Is the vulnerable path exposed to untrusted input?
4. **How urgent is it?** Weigh severity, whether it is known to be exploited, whether exploitation needs network access or authentication, and how exposed this system is.

Sort the results:

- **Fix now**: reachable and serious, or known to be exploited.
- **Fix in normal flow**: real but low exposure.
- **Not affected**: with the specific reason (not present, not in range, code not reachable, not shipped).
- **Needs a human decision**: no fix exists, or the fix is a breaking change.

"Not reachable" must rest on something you checked. If you are unsure, treat it as reachable.

## 2. Choose the smallest effective fix

Prefer, in this order:

1. **Patch-level upgrade** of the affected package to the nearest fixed version.
2. **Minor upgrade**, after reading the changelog for behavior changes.
3. **For transitive dependencies**: upgrade the direct parent that brings it in. Use an override or resolution pin only when no parent release has the fix, and leave a comment saying when it can be removed.
4. **For container images**: move to a newer tag or digest of the same base image line, then rebuild. Remove packages the application does not need rather than patching them.
5. **Major upgrade or replacement**: propose it with the migration cost and wait for approval.
6. **For flaws in first-party code**: fix the root cause (validate, parameterize, encode, authorize), then look for the same pattern elsewhere in the codebase and fix those too.
7. **Mitigation when no fix exists**: disable the affected feature, tighten configuration, or add a compensating control, and document it as temporary.

Do one finding, or one tightly related group, per change. Small, single-purpose upgrades are easy to review, easy to verify and easy to revert. Avoid "upgrade everything" changes; they bury the security fix under unrelated risk.

Check that the fixed version is a real published release from the legitimate package, and keep it pinned in the lockfile. Do not turn off the scanner, add a blanket ignore, or lower the gate threshold to make the finding disappear.

## 3. Verify the fix

1. Regenerate the lockfile and confirm the resolved version is the fixed one everywhere it appears (multiple versions of one package often coexist).
2. Run the full test suite and the build. Upgrades break things in places the diff does not show.
3. Re-run the scanner and confirm the finding is gone and no new ones arrived with the upgrade.
4. For code fixes, add a test that fails on the old code and passes on the new.

If you could not run a step, say so and give the command. Never report a finding as fixed without a re-scan that you or the person actually ran.

If the upgrade breaks tests, find out whether the breakage is a real behavior change that needs a code adjustment or a reason to choose a different fix. Report it either way instead of forcing it through.

## 4. Report

```
## Summary
N findings: X fixed, Y not affected, Z need a decision.

## Findings
| ID | Component (version) | Severity | Reachable? | Decision | Fix |
One row per finding.

## Changes made
Package: old version -> new version, why this version, files changed.

## Evidence
Scanner before and after, test and build results.
Or: "Not executed. Run: <commands>."

## Not fixed
For each: why, the risk in plain language, the mitigation in place,
and the condition or date for revisiting.

## Needs a decision
What is being asked, the options, and your recommendation.
```

For anything left unfixed, write the justification so a security reviewer can accept or reject it on its own: what the finding is, why it is or is not exploitable here, what limits the impact, and what would change the assessment. If the organization uses a formal exception format (a VEX statement, a risk acceptance, a plan of action and milestones entry), offer to draft it in that format; the person supplies the template.

Do not commit, push, open pull requests, rebuild shared images or deploy unless asked. Accepting a risk is always the person's decision, never yours.

## Working through the relay harness

Some teams run this skill in a chat window with no repository access and use a
local harness, `relay`, to act on the repository. You will recognize it when the
input starts with `# RELAY TURN`.

- Turn 1 contains the task, the repository, the tools you may request, and a
  **Protocol** section. Follow the protocol exactly: a short explanation, then
  one four-backtick code block of `=== CALL tool name=value ===` lines.
- You act only through those tools. Nothing has run unless a result says so, and
  a file is written exactly as you send it, so never send fragments or diffs.
- A person may be carrying each turn by hand. Ask for everything you need in one
  reply. When you know what to write, send the files and request the check in
  the same reply, tests included.
- Results marked refused or denied are final. Files listed as withheld were kept
  back on purpose. Adapt, or use the ask tool. Never ask for credentials.
- If the same check fails three times, stop and use the ask tool to explain what
  you think is wrong instead of sending another guess.
- Call finish only after a check has passed since your last change.
