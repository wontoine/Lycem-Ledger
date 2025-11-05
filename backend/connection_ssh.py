"""
SSH tunnel helper for connecting to remote MongoDB.

Usage patterns:

- Set environment variables (see list below) and enable the tunnel with
  `SSH_TUNNEL=1` or `SSH_TUNNEL_ENABLE=1`. Importing settings will then
  call `ensure_ssh_tunnel_if_enabled()` before MongoEngine connects.

- Alternatively, import and call `ensure_ssh_tunnel_if_enabled()` early in
  your own bootstrap code.

Environment variables:
  SSH_TUNNEL or SSH_TUNNEL_ENABLE   -> true/false to enable
  SSH_HOST                           -> SSH server hostname
  SSH_PORT                           -> SSH server port (default 22)
  SSH_USERNAME                       -> SSH username
  SSH_PASSWORD                       -> SSH password (optional if key used)
  SSH_PKEY_PATH                      -> Path to private key (optional)
  SSH_PKEY_PASSPHRASE                -> Passphrase for private key (optional)
  REMOTE_MONGO_HOST                  -> Remote MongoDB host (default 127.0.0.1)
  REMOTE_MONGO_PORT                  -> Remote MongoDB port (default 27017)
  LOCAL_BIND_HOST                    -> Local bind host (default 127.0.0.1)
  LOCAL_BIND_PORT                    -> Local bind port (default 27018 or MONGODB_PORT)

Requires: sshtunnel (and paramiko). Add to requirements: sshtunnel.
"""

from __future__ import annotations

import os
import atexit
from typing import Optional

try:
    from sshtunnel import SSHTunnelForwarder  # type: ignore
except Exception:
    SSHTunnelForwarder = None  # type: ignore

_tunnel: Optional["SSHTunnelForwarder"] = None


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_tunnel_running() -> bool:
    global _tunnel
    try:
        return _tunnel is not None and bool(getattr(_tunnel, "is_active", False))
    except Exception:
        return False


def stop_ssh_tunnel() -> None:
    global _tunnel
    try:
        if _tunnel is not None:
            _tunnel.stop()
    except Exception:
        pass
    finally:
        _tunnel = None


def ensure_ssh_tunnel_if_enabled():
    """
    Start an SSH local port forward if enabled via env.

    Returns the forwarder instance when started, or None otherwise.
    Never raises: logs and returns if configuration/imports are missing.
    """
    global _tunnel
    enabled = _parse_bool(os.environ.get("SSH_TUNNEL") or os.environ.get("SSH_TUNNEL_ENABLE"))
    if not enabled:
        return None

    # Already running
    if is_tunnel_running():
        return _tunnel

    if SSHTunnelForwarder is None:
        print("SSH tunnel requested but 'sshtunnel' is not installed. Skipping.")
        return None

    ssh_host = os.environ.get("SSH_HOST")
    ssh_port = int(os.environ.get("SSH_PORT", 22))
    ssh_username = os.environ.get("SSH_USERNAME")
    ssh_password = os.environ.get("SSH_PASSWORD")
    ssh_pkey_path = os.environ.get("SSH_PKEY_PATH")
    ssh_pkey_passphrase = os.environ.get("SSH_PKEY_PASSPHRASE")

    remote_host = os.environ.get("REMOTE_MONGO_HOST", "127.0.0.1")
    remote_port = int(os.environ.get("REMOTE_MONGO_PORT", 27017))
    local_host = os.environ.get("LOCAL_BIND_HOST", "127.0.0.1")
    local_port = int(os.environ.get("LOCAL_BIND_PORT", os.environ.get("MONGODB_PORT", 27018)))

    # Minimal validation
    if not ssh_host or not ssh_username:
        print("SSH tunnel enabled but SSH_HOST or SSH_USERNAME not set. Skipping.")
        return None
    if not ssh_password and not ssh_pkey_path:
        print("SSH tunnel enabled but neither SSH_PASSWORD nor SSH_PKEY_PATH provided. Skipping.")
        return None

    # Build kwargs for sshtunnel (only supported args)
    kwargs = {
        "ssh_username": ssh_username,
        "remote_bind_address": (remote_host, remote_port),
        "local_bind_address": (local_host, local_port),
    }
    if ssh_password:
        kwargs["ssh_password"] = ssh_password
    if ssh_pkey_path:
        kwargs["ssh_pkey"] = ssh_pkey_path
    if ssh_pkey_passphrase:
        kwargs["ssh_private_key_password"] = ssh_pkey_passphrase

    try:
        _tunnel = SSHTunnelForwarder((ssh_host, ssh_port), **kwargs)  # type: ignore[arg-type]
        _tunnel.start()
        atexit.register(stop_ssh_tunnel)
        print(
            "SSH tunnel started: {local_host}:{local_port} -> {remote_host}:{remote_port} via {ssh_host}:{ssh_port}"
        )
        return _tunnel
    except Exception as e:
        print(f"Failed to start SSH tunnel: {e}")
        stop_ssh_tunnel()
        return None


__all__ = [
    "ensure_ssh_tunnel_if_enabled",
    "stop_ssh_tunnel",
    "is_tunnel_running",
]
