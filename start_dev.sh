sh start_dev.sh

# Simple helper script to start the Django backend first, then the Vite frontend.
# Usage:
#   bash start_dev.sh

set -euo pipefail

# Ensure we run from the repository root (the folder containing manage.py and package.json)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Django backend (http://127.0.0.1:8000)..."

# Start Django in the background
python manage.py runserver 0.0.0.0:8000 &
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
  curl -s "http://127.0.0.1:8000" >/dev/null || true
fi

echo "Starting Vite frontend (npm run dev → http://127.0.0.1:5173)..."

# If node_modules is missing, suggest installation
if [ ! -d node_modules ]; then
  echo "node_modules not found. Installing dependencies with 'npm install'..."
  npm install
fi

# Run the frontend in the foreground so Ctrl+C stops it; the trap will stop Django
npm run dev
