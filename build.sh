#!/bin/bash

# Install dependencies
echo "Installing project dependencies..."
npm i gettext
export PATH=/python312/bin:$PATH
export UV_PYTHON=3.12
export UV_LINK_MODE=copy
uv venv && uv pip install .

# Make migrations
echo "Making migrations..."
uv run python manage.py makemigrations --noinput
uv run python manage.py migrate --noinput

# Collect staticfiles
echo "Collect static..."
uv run python manage.py collectstatic --noinput --clear

echo "Build process completed!"
