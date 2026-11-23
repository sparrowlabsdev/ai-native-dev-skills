#!/usr/bin/env python3
"""Check every skill against the Agent Skills format and Gemini Enterprise upload limits.

Standard library only. Usage: python3 scripts/validate.py [skills_dir]
"""
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MAX_NAME, MAX_DESC, MAX_BODY = 64, 1024, 500_000


def check(skill_dir: Path) -> list[str]:
    errors = []
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        return ["missing SKILL.md"]
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not match:
        return ["frontmatter must start the file and be enclosed in --- lines"]
    front, body = match.groups()
    fields = dict(re.findall(r"^([a-z]+):[ \t]*(.*)$", front, re.M))

    name = fields.get("name", "").strip("\"'")
    if not name:
        errors.append("name is required")
    else:
        if not NAME_RE.fullmatch(name) or len(name) > MAX_NAME:
            errors.append(f"name '{name}' must be 1-{MAX_NAME} chars: lowercase letters, numbers, single hyphens")
        if name != skill_dir.name:
            errors.append(f"name '{name}' must match folder '{skill_dir.name}'")

    desc = fields.get("description", "").strip("\"'")
    if not desc:
        errors.append("description is required (single line)")
    elif len(desc) > MAX_DESC:
        errors.append(f"description is {len(desc)} chars (max {MAX_DESC})")

    if not body.strip():
        errors.append("instruction body is empty")
    elif len(body) > MAX_BODY:
        errors.append(f"body is {len(body)} chars (max {MAX_BODY})")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "skills")
    skills = sorted(p for p in root.iterdir() if p.is_dir())
    if not skills:
        print(f"no skills found in {root}")
        return 1
    failed = 0
    for skill in skills:
        errors = check(skill)
        print(f"{'FAIL' if errors else 'ok  '}  {skill.name}")
        for e in errors:
            print(f"        {e}")
        failed += bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
