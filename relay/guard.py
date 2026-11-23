"""What the model may read and where it may write."""
from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path, PurePosixPath

PROTECTED_TOP = (".git", ".relay", ".beads")

SECRET_NAME_GLOBS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "*.tfstate", "*.tfstate.*", "*.tfvars", "*.tfvars.json", "*.pkrvars.hcl",
    "*.pkrvars.json", "*id_rsa*", "*id_ed25519*", ".netrc", ".npmrc", ".pypirc",
    "*credentials*", "*secret*", "*.kdbx",
]

SECRET_CONTENT = re.compile(
    r"AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|gh[pousr]_[A-Za-z0-9]{36}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
)


class Refused(Exception):
    """The request is outside what policy allows. The message goes to the model."""


def _matches(rel: str, globs) -> bool:
    name = PurePosixPath(rel).name
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(name, g) for g in globs)


def is_protected(rel: str) -> bool:
    top = PurePosixPath(rel).parts[0] if PurePosixPath(rel).parts else ""
    return top in PROTECTED_TOP or top.startswith(".beads.")


def safe_rel(root: Path, raw: str, policy: dict) -> str:
    """Validate a model-supplied path and return it as a clean relative path."""
    text = (raw or "").strip().strip("`")
    if not text:
        raise Refused("empty path")
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise Refused(f"{text}: use a relative path with forward slashes")
    parts = PurePosixPath(text).parts
    if ".." in parts:
        raise Refused(f"{text}: path leaves the repository")
    rel = str(PurePosixPath(*parts)) if parts else ""
    if not rel or rel == ".":
        raise Refused("empty path")
    if is_protected(rel):
        raise Refused(f"{rel}: {parts[0]} is off limits")
    if _matches(rel, policy.get("deny_path_globs", [])):
        raise Refused(f"{rel}: denied by policy")
    target = root / rel
    if target.is_symlink():
        raise Refused(f"{rel}: is a symlink")
    ancestor = target.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    root_real = root.resolve()
    real = ancestor.resolve()
    if real != root_real and root_real not in real.parents:
        raise Refused(f"{rel}: resolves outside the repository")
    return rel


def unreadable_reason(root: Path, rel: str, policy: dict) -> str | None:
    """Why this file's content must not be shown to the model, or None."""
    allowed = _matches(rel, policy.get("allow_name_globs", []))
    globs = SECRET_NAME_GLOBS + list(policy.get("secret_name_globs", []))
    if not allowed and _matches(rel, globs):
        return "name matches the secret filter"
    path = root / rel
    if not path.is_file():
        return "not a file"
    size = path.stat().st_size
    if size > int(policy.get("max_file_kb", 200)) * 1024:
        return f"larger than {policy.get('max_file_kb', 200)} KB"
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return "binary"
    if SECRET_CONTENT.search(data.decode("utf-8", errors="replace")):
        return "looks like it contains a credential"
    return None


def repo_files(root: Path, policy: dict, under: str = "") -> list[str]:
    """Tracked and untracked-but-not-ignored files, minus protected paths."""
    cmd = ["git", "ls-files", "-co", "--exclude-standard", "-z"]
    if under:
        cmd += ["--", under]
    out = subprocess.run(cmd, cwd=str(root), capture_output=True, check=False).stdout
    files = [f for f in out.decode("utf-8", errors="replace").split("\0") if f]
    deny = policy.get("deny_path_globs", [])
    return sorted(f for f in files if not is_protected(f) and not _matches(f, deny))
