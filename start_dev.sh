sh start_dev.sh

# Simple helper script to start the Django backend first, then the Vite frontend.
# Usage:
#   bash start_dev.sh

set -euo pipefail

# Ensure we run from the repository root (the folder containing manage.py and package.json)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

# Allow overriding backend host/port for local dev. Default to Django's standard port 8000
# so it matches existing frontend calls to http://127.0.0.1:8000/.
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

echo "Starting Django backend (http://127.0.0.1:${BACKEND_PORT})..."

# Start Django in the background
python manage.py runserver "${BACKEND_HOST}:${BACKEND_PORT}" &
DJANGO_PID=$!

cleanup() {
  echo
  echo "Shutting down services..."
  if kill -0 "$DJANGO_PID" 2>/dev/null; then
    kill "$DJANGO_PID" 2>/dev/null || true
    wait "$DJANGO_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

# Give the backend a moment to start up
sleep 2

if command -v curl >/dev/null 2>&1; then
  # Try a quick health check (best-effort)
  curl -s "http://127.0.0.1:${BACKEND_PORT}" >/dev/null || true
fi

echo "Starting Vite frontend (npm run dev → http://127.0.0.1:3003)..."

# If node_modules is missing, suggest installation
if [ ! -d node_modules ]; then
  echo "node_modules not found. Installing dependencies with 'npm install'..."
  npm install
fi

# Run the frontend in the foreground so Ctrl+C stops it; the trap will stop Django
npm run dev
