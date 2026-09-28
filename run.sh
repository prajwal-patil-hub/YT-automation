#!/usr/bin/env bash
# Convenience wrapper so you can type ./run.sh instead of python3 -m pipeline.cli
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m pipeline.cli "$@"
