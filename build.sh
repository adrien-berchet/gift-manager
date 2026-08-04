#!/bin/bash
set -euo pipefail

echo "Installing project dependencies..."
export PATH=/python312/bin:$PATH
export UV_PYTHON=3.12
export UV_LINK_MODE=copy
uv sync --frozen --no-dev

echo "Collect static..."
DJANGO_SETTINGS_MODULE=GiftManager.settings.build uv run --frozen python manage.py collectstatic --noinput --clear

echo "Build process completed!"
