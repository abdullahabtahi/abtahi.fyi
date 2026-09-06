import os
import sqlite3
import functools
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, Path, HTTPException, Response
from pydantic import BaseModel

from app.schemas.feeds import (
    PublicItem,
    ItemType,
    SearchResult,
    GraphSnapshot,
)
from app.core.public_loader import PublicContentLoader
from app.core.network import network_cache
from app.core.db import init_sqlite_db

router = APIRouter(prefix="/api/fyi/q", tags=["Public Query API"])

loader = PublicContentLoader()

def get_db_connection() -> sqlite3.Connection:
    db_path = os.environ.get("DB_PATH", "data/graph.db")
    conn = init_sqlite_db(db_path)
    # Ensure FTS is populated if empty
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM public_items_fts;")
    count = cursor.fetchone()[0]
    if count == 0:
        loader.index_fts(conn)
    return conn

# --- 1. Dual-Routing Keyword Search ---

def _execute_fts_search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchResult]:
    items = loader.load_all_items()
    item_map = {item.id: item for item in items}
    
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    cursor = conn.cursor()
    results: list[SearchResult] = []
    
    # Try FTS5 MATCH with sanitized terms
    sanitized = " ".join([f'"{term.replace('"', '')}"*' for term in cleaned_query.split() if term])
    try:
        cursor.execute(
            """
            SELECT id, rank, snippet(public_items_fts, 4, '<b>', '</b>', '...', 15)
            FROM public_items_fts
            WHERE public_items_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """,
            (sanitized, limit),
        )
        rows = cursor.fetchall()
        for item_id, rank, snippet in rows:
            if item_id in item_map:
                item = item_map[item_id]
                results.append(
                    SearchResult(
                        id=item.id,
                        title=item.title,
                        item_type=item.item_type,
                        permalink=f"/i/{item.id}",
                        score=float(abs(rank)),
                        snippet=snippet or item.summary or item.title,
                        fallback=False,
                    )
                )
    except Exception:
        # Fallback to simple LIKE search if FTS syntax error
        for item in items:
            text = f"{item.title} {item.summary or ''} {item.raw_markdown}".lower()
            if cleaned_query.lower() in text:
                results.append(
                    SearchResult(
                        id=item.id,
                        title=item.title,
                        item_type=item.item_type,
                        permalink=f"/i/{item.id}",
                        score=1.0,
                        snippet=item.summary or item.title,
                        fallback=True,
                    )
                )
    return results

@router.get("/search/{term}", response_model=List[SearchResult])
async def search_items_path(term: str = Path(..., description="Search keyword")):
    conn = get_db_connection()
    try:
        return _execute_fts_search(conn, term)
    finally:
        conn.close()

@router.get("/search", response_model=List[SearchResult])
async def search_items_query(q: str = Query(..., description="Search keyword query")):
    conn = get_db_connection()
    try:
        return _execute_fts_search(conn, q)
    finally:
        conn.close()

# --- 2. Dual-Routing Semantic Search with FTS5 Fallback ---

@functools.lru_cache(maxsize=512)
def _get_query_embedding_cached(query_text: str) -> Optional[list[float]]:
    try:
        from app.ai.client import get_genai_client
        client = get_genai_client()
        resp = client.models.embed_content(
            model="text-embedding-004",
            contents=query_text,
        )
        if hasattr(resp, "embedding") and resp.embedding:
            return resp.embedding.values
        elif hasattr(resp, "embeddings") and resp.embeddings:
            return resp.embeddings[0].values
    except Exception:
        return None
    return None

def _execute_semantic_search(conn: sqlite3.Connection, query: str, limit: int = 10) -> tuple[list[SearchResult], bool]:
    embedding = _get_query_embedding_cached(query)
    
    # Graceful fallback to FTS5 keyword search if embedding unavailable
    if embedding is None:
        fts_results = _execute_fts_search(conn, query, limit=limit)
        return [r.model_copy(update={"fallback": True}) for r in fts_results], True

    # Vector search query via sqlite-vec
    items = loader.load_all_items()
    item_map = {item.id: item for item in items}
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT item_id, distance
            FROM vec_items
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?;
            """,
            (str(embedding), limit),
        )
        rows = cursor.fetchall()
        results = []
        for item_id, distance in rows:
            if item_id in item_map:
                item = item_map[item_id]
                score = round(1.0 - float(distance), 4)
                results.append(
                    SearchResult(
                        id=item.id,
                        title=item.title,
                        item_type=item.item_type,
                        permalink=f"/i/{item.id}",
                        score=max(0.0, score),
                        snippet=item.summary or item.title,
                        fallback=False,
                    )
                )
        if not results:
            fts_results = _execute_fts_search(conn, query, limit=limit)
            return [r.model_copy(update={"fallback": True}) for r in fts_results], True
        return results, False
    except Exception:
        # If vector table query fails, fallback to FTS5
        fts_results = _execute_fts_search(conn, query, limit=limit)
        return [r.model_copy(update={"fallback": True}) for r in fts_results], True

@router.get("/semantic/{query}", response_model=List[SearchResult])
async def semantic_search_path(response: Response, query: str = Path(..., description="Semantic search phrase")):
    conn = get_db_connection()
    try:
        results, is_fallback = _execute_semantic_search(conn, query)
        if is_fallback:
            response.headers["X-Search-Fallback"] = "true"
        return results
    finally:
        conn.close()

@router.get("/semantic", response_model=List[SearchResult])
async def semantic_search_query(response: Response, q: str = Query(..., description="Semantic search phrase")):
    conn = get_db_connection()
    try:
        results, is_fallback = _execute_semantic_search(conn, q)
        if is_fallback:
            response.headers["X-Search-Fallback"] = "true"
        return results
    finally:
        conn.close()

# --- 3. Dual-Routing Knowledge Connections (Edges) ---

@router.get("/edges/{item_id}")
async def get_edges_path(item_id: str = Path(..., description="Target item identifier")):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    edges = network_cache.get_item_edges(item_id)
    return edges

@router.get("/edges")
async def get_edges_query(itemId: str = Query(..., description="Target item identifier")):
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    edges = network_cache.get_item_edges(itemId)
    return edges

# --- 4. Items Endpoints ---

@router.get("/items", response_model=List[PublicItem])
async def get_items(
    since: Optional[str] = Query(None, description="Filter items published after ISO datetime"),
    type: Optional[str] = Query(None, description="Filter by ItemType (riff, link, essay)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    items = loader.load_all_items()

    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            items = [i for i in items if i.published_at >= since_dt]
        except ValueError:
            pass

    if type:
        items = [i for i in items if i.item_type.value == type.lower()]

    return items[offset : offset + limit]

@router.get("/items/{item_id}", response_model=PublicItem)
async def get_item_detail(item_id: str = Path(..., description="Target item identifier")):
    items = loader.load_all_items()
    item = next((i for i in items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail=f"Public item '{item_id}' not found")
    return item

# --- 5. Graph Intelligence Summary Snapshot (<15ms) ---

@router.get("/summary", response_model=GraphSnapshot)
async def get_graph_summary():
    # Attempt to load from in-memory cache or SQLite snapshot
    items = loader.load_all_items()
    network_cache.load_from_items(items)
    return network_cache.get_snapshot()
