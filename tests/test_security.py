import pytest
from app.core.security import validate_outbound_url

def test_validate_outbound_url_valid():
    assert validate_outbound_url("https://example.com/feed.xml") is True
    assert validate_outbound_url("http://rss.cnn.com/rss/cnn_topstories.rss") is True

def test_validate_outbound_url_invalid_scheme():
    assert validate_outbound_url("ftp://example.com/feed") is False
    assert validate_outbound_url("file:///etc/passwd") is False

def test_validate_outbound_url_loopback():
    assert validate_outbound_url("http://127.0.0.1/admin") is False
    assert validate_outbound_url("http://localhost:8080/metrics") is False

def test_validate_outbound_url_metadata():
    assert validate_outbound_url("http://169.254.169.254/computeMetadata/v1/") is False

def test_validate_outbound_url_rfc1918():
    assert validate_outbound_url("http://10.0.0.1/internal") is False
    assert validate_outbound_url("http://172.16.0.5/api") is False
    assert validate_outbound_url("http://192.168.1.100/feed") is False


@pytest.mark.parametrize(
    "url",
    [
        "http://100.64.0.1/feed",
        "http://0.0.0.0/feed",
        "http://224.0.0.1/feed",
        "http://[::1]/feed",
    ],
)
def test_validate_outbound_url_rejects_non_public_address_ranges(url: str):
    assert validate_outbound_url(url) is False

def test_validate_outbound_url_invalid_hostname():
    assert validate_outbound_url("https://this-domain-does-not-exist-123456789.com") is False
