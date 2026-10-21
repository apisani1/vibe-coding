#!/usr/bin/env bash
# Seed only the approved spec (no design.md), so `plan` has no upstream design.
set -euo pipefail
bash "$(dirname "$0")/../09-design-mdtoc-cli/scaffold.sh"
