import sqlite3
import sqlite_vec
from pathlib import Path

def init_sqlite_db(db_path: str = "data/graph.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    
    # Production Data Engineering Pragmas
    conn.execute("PRAGMA journal_mode = WAL;")        # Non-blocking concurrent readers during write
    conn.execute("PRAGMA synchronous = NORMAL;")      # 2-3x write throughput improvement; safe in WAL
    conn.execute("PRAGMA busy_timeout = 5000;")       # Wait up to 5s before lock failure
    conn.execute("PRAGMA foreign_keys = ON;")         # Enforce relational integrity
    conn.execute("PRAGMA cache_size = -64000;")       # Allocate 64MB memory page cache
    conn.execute("PRAGMA temp_store = MEMORY;")       # In-memory temporary tables & sorting
    
    # Initialize Virtual Tables
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(
          item_id TEXT PRIMARY KEY,
          embedding float[768] distance_metric=cosine
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_concepts USING vec0(
          concept_id TEXT PRIMARY KEY,
          embedding float[768] distance_metric=cosine
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
          chunk_id TEXT PRIMARY KEY,
          embedding float[768] distance_metric=cosine
        );
    """)

    # Full-Text Search Virtual Table (FTS5) for keyword queries and fallback
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS public_items_fts USING fts5(
            id UNINDEXED,
            title,
            summary,
            commentary,
            content,
            tags,
            tokenize = 'porter unicode61'
        );
    """)

    # Persistent Graph Snapshot Table for Sub-Millisecond Cold Boot
    conn.execute("""
        CREATE TABLE IF NOT EXISTS public_graph_snapshot (
            snapshot_key TEXT PRIMARY KEY,
            snapshot_json TEXT NOT NULL,
            generated_at TEXT NOT NULL
        );
    """)
    
    return conn
