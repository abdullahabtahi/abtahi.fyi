import pytest

from app.ingest.poller import PollFailure, poll_feed
from app.models.feed import ApprovedFeed


@pytest.mark.asyncio
async def test_poller_rejects_an_unsafe_redirect_before_returning_content():
    feed = ApprovedFeed(id="feed-1", url="https://example.com/feed.xml")

    class Response:
        status_code = 302
        headers = {"Location": "http://127.0.0.1/private"}

    class Client:
        async def get(self, url, **kwargs):
            return Response()

    result = await poll_feed(
        feed,
        client=Client(),
        validator=lambda url: (_ for _ in ()).throw(ValueError("unsafe target"))
        if "127.0.0.1" in url
        else url,
    )

    assert result.failure is PollFailure.UNSAFE_TARGET
    assert result.content is None
