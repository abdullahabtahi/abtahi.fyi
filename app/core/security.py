import os
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
    """SSRF Guardrail: Rejects loopback, private RFC 1918, and Cloud Metadata IPs"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        return False
        
    # Block loopback, link-local (GCP metadata), and private ranges
    if ip.startswith(("127.", "169.254.", "10.", "192.168.")) or (
        ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31
    ):
        return False
    return True
