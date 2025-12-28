import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from backend import connection_ssh


class ConnectionSSHTests(SimpleTestCase):
    def tearDown(self):
        connection_ssh.stop_ssh_tunnel()

    def test_tunnel_starts_with_valid_turing_config(self):
        """
        Verifies that enabling the tunnel spins up an SSHTunnelForwarder with the Turing host.
        """
        env = {
            "SSH_TUNNEL": "1",
            "SSH_HOST": "turing.cs.olemiss.edu",
            "SSH_PORT": "2222",
            "SSH_USERNAME": "lyceum",
            "SSH_PASSWORD": "secret",
            "REMOTE_MONGO_HOST": "127.0.0.2",
            "REMOTE_MONGO_PORT": "27017",
            "LOCAL_BIND_HOST": "127.0.0.1",
            "LOCAL_BIND_PORT": "27018",
        }
        with patch.dict(os.environ, env, clear=True):
            forwarder = MagicMock()
            with patch("backend.connection_ssh.SSHTunnelForwarder", return_value=forwarder) as mock_forwarder:
                result = connection_ssh.ensure_ssh_tunnel_if_enabled()

        self.assertIs(result, forwarder)
        mock_forwarder.assert_called_once_with(
            ("turing.cs.olemiss.edu", 2222),
            ssh_username="lyceum",
            ssh_password="secret",
            remote_bind_address=("127.0.0.2", 27017),
            local_bind_address=("127.0.0.1", 27018),
        )
        forwarder.start.assert_called_once()

    def test_tunnel_not_started_when_credentials_missing(self):
        """
        Without credentials the helper should refuse to start a tunnel.
        """
        env = {
            "SSH_TUNNEL": "1",
            "SSH_HOST": "turing.cs.olemiss.edu",
            "SSH_USERNAME": "",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("backend.connection_ssh.SSHTunnelForwarder") as mock_forwarder:
                result = connection_ssh.ensure_ssh_tunnel_if_enabled()

        self.assertIsNone(result)
        mock_forwarder.assert_not_called()
