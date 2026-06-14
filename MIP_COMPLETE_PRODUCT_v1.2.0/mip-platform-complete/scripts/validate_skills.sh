#!/usr/bin/env bash
set -euo pipefail

if command -v skills-ref >/dev/null 2>&1; then
  for skill in skills/*; do
    [ -d "$skill" ] || continue
    skills-ref validate "$skill"
  done
else
  echo "skills-ref is not installed."
  echo "Install the Agent Skills reference validator, then rerun this script."
  exit 2
fi
