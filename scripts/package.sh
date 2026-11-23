#!/usr/bin/env bash
# Build one uploadable ZIP per skill into dist/ (for the Gemini Enterprise web app).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/scripts/validate.py" "$root/skills"
rm -rf "$root/dist" && mkdir -p "$root/dist"
cd "$root/skills"
for dir in */; do
  name="${dir%/}"
  zip -qr "$root/dist/$name.zip" "$name" -x '*.DS_Store'
  echo "built dist/$name.zip"
done
