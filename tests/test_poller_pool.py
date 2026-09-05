import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.models.feed import FeedSource
from app.ingest.poller import poll_feed, poll_semaphore, process_feed

@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    feeds = [
        FeedSource(id=str(i), url=f"https://example.com/feed{i}.xml", last_fetched_at=None, etag=None, last_modified=None)
        for i in range(10)
    ]
    
    active_polls = 0
    max_active_polls = 0
    
    async def mock_poll_feed_impl(*args, **kwargs):
        nonlocal active_polls, max_active_polls
        active_polls += 1
        if active_polls > max_active_polls:
            max_active_polls = active_polls
        
        # simulate network delay
        await asyncio.sleep(0.1)
        
        active_polls -= 1
        return (None, 200, None, None)
    
    with patch("app.ingest.poller.httpx.AsyncClient.get") as mock_get:
        mock_get.return_value.status_code = 200
        # Wait, poll_feed itself acquires the semaphore, not process_feed.
        # Actually poll_feed uses httpx. Let's patch httpx.get or we can patch the AsyncClient completely.
        # It's easier to mock poll_feed, but poll_feed is where the semaphore is.
        pass

    # We will just patch httpx.AsyncClient.__aenter__ to return a mock client
    # and the client.get will be our tracked function.
    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def get(self, *args, **kwargs):
            nonlocal active_polls, max_active_polls
            active_polls += 1
            max_active_polls = max(max_active_polls, active_polls)
            await asyncio.sleep(0.1)
            active_polls -= 1
            
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.text = "<rss></rss>"
            mock_response.raise_for_status = lambda: None
            return mock_response
            
    with patch("app.ingest.poller.httpx.AsyncClient", return_value=MockClient()):
        tasks = [poll_feed(f) for f in feeds]
        await asyncio.gather(*tasks)
        
    # The semaphore is set to 5. So max_active_polls should not exceed 5.
    assert max_active_polls <= 5

@pytest.mark.asyncio
async def test_worker_pool_handles_failures_gracefully():
    feed_success = FeedSource(id="1", url="https://example.com/success.xml")
    feed_fail = FeedSource(id="2", url="https://example.com/fail.xml")
    
    async def mock_process_feed(feed):
        if feed.id == "2":
            raise ValueError("Simulated processing crash")
        return [1, 2, 3] # chunks
        
    with patch("app.ingest.poller.process_feed", side_effect=mock_process_feed):
        from app.ingest.poller import run_poller_pool
        results = await run_poller_pool([feed_success, feed_fail, feed_success])
        
        # We expect it to return chunks. feed_success returns [1, 2, 3] and feed_fail returns [].
        # So total chunks should be [1, 2, 3, 1, 2, 3]
        assert len(results) == 6
        assert results == [1, 2, 3, 1, 2, 3]
