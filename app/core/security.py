import os
import socket
import ipaddress
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
    """SSRF Guardrail: Rejects loopback, private RFC 1918, and Cloud Metadata IPs"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        ip_addr_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_addr_str)
    except (socket.gaierror, ValueError):
        return False
        
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified:
        return False

    return True
