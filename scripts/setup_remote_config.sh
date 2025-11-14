#!/bin/bash
# Setup Firebase Remote Config for character visibility management
# Usage: bash backend/scripts/setup_remote_config.sh [--all-characters] [--no-hard-blocking] [--dry-run]

set -e

cd "$(dirname "$0")/../.." || exit 1
source backend/venv/bin/activate

python3 backend/scripts/setup_remote_config.py "$@"

