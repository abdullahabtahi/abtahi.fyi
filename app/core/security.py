import os
import ipaddress
import socket
from urllib.parse import urlparse
from google.cloud import secretmanager

def get_secret(secret_id: str, default: str | None = None) -> str:
    env_val = os.getenv(secret_id)
    if env_val:
        return env_val

    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        if default is not None:
            return default
        raise ValueError(f"Neither {secret_id} nor GCP_PROJECT_ID set.")

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        if default is not None:
            return default
        raise RuntimeError(f"Failed to access secret {secret_id} from Secret Manager: {e}")

def validate_outbound_url(url: str) -> bool:
    """Returns whether a URL resolves exclusively to public HTTP(S) addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False

    def is_public(address: tuple) -> bool:
        ip = ipaddress.ip_address(address[4][0])
        return ip.is_global and not ip.is_multicast

    return bool(addresses) and all(is_public(address) for address in addresses)
