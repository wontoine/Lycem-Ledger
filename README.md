<<<<<<< Updated upstream
<<<<<<< Updated upstream
# Lycem-Ledger
=======
=======
>>>>>>> Stashed changes
# Lycem-Ledger

## Frontend (React + Vite)

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh
# Lyceum Ledger

## Ports used in development

- Frontend (Vite + React): http://127.0.0.1:3003
- Backend (Django): http://127.0.0.1:8080

Why port 8080 now?
- Port 8000 was in use on some environments. We now default to 8080 for the backend during development to avoid conflicts, while keeping an easy way to override it.

Can I change it?
- Yes. Our start_dev.sh supports overriding the backend host/port with environment variables:
  - BACKEND_HOST (default: 0.0.0.0)
  - BACKEND_PORT (default: 8080)

Examples:
```bash
# Run backend on port 9000
BACKEND_PORT=9000 bash start_dev.sh

# Custom host and port
BACKEND_HOST=127.0.0.1 BACKEND_PORT=9000 bash start_dev.sh
```

Notes:
- The frontend runs on port 3003 (configured in vite.config.js). CORS/CSRF settings on the backend already trust common local dev origins, including http://127.0.0.1:3003 and http://localhost:3003.
- Changing the backend port does not typically require CORS changes, since CORS cares about the frontend’s origin, not the backend’s listening port.
- If you run Django directly without the script, you can still specify a port: `python manage.py runserver 0.0.0.0:8080` (replace 8080 as needed).
