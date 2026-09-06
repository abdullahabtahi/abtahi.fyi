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

class UnsafeOutboundTarget(ValueError):
    """An outbound target is malformed or does not resolve exclusively publicly."""


def validate_outbound_target(url: str, resolver=socket.getaddrinfo) -> str:
    """Return a safe HTTP(S) URL after rejecting every non-public resolution."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or parsed.username or parsed.password:
        raise UnsafeOutboundTarget("unsupported outbound URL")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeOutboundTarget("outbound URL has no hostname")

    try:
        addresses = resolver(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeOutboundTarget("outbound hostname cannot be resolved") from None

    def is_public(address: tuple) -> bool:
        ip = ipaddress.ip_address(address[4][0])
        return ip.is_global and not ip.is_multicast

    if not addresses or not all(is_public(address) for address in addresses):
        raise UnsafeOutboundTarget("outbound hostname is not exclusively public")
    return url


def validate_outbound_url(url: str) -> bool:
    """Compatibility helper returning whether a target is safe to request."""
    try:
        validate_outbound_target(url)
    except (UnsafeOutboundTarget, ValueError):
        return False
    return True
