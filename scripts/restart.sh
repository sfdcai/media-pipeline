#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/stop.sh" ]]; then
  "$SCRIPT_DIR/stop.sh" || true
fi

"$SCRIPT_DIR/run.sh"
