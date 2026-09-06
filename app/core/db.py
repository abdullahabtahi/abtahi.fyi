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

    # 1. Audit log of pruned/archived graph edges
    conn.execute("""
        CREATE TABLE IF NOT EXISTS archived_edges (
            edge_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            final_confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            last_reinforced_at TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT (datetime('now')),
            reason TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archived_edges_source ON archived_edges(source_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archived_edges_target ON archived_edges(target_id);")

    # 2. Discovered triangular contradiction cycles
    conn.execute("""
        CREATE TABLE IF NOT EXISTS triangular_tensions (
            triad_id TEXT PRIMARY KEY,
            node_a TEXT NOT NULL,
            node_b TEXT NOT NULL,
            node_c TEXT NOT NULL,
            edge_ab_type TEXT NOT NULL,
            edge_bc_type TEXT NOT NULL,
            edge_ca_type TEXT NOT NULL,
            contradiction_summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            detected_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triangular_nodes ON triangular_tensions(node_a, node_b, node_c);")

    # 3. Consolidation Run History & Performance Metrics
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consolidation_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            dry_run INTEGER NOT NULL DEFAULT 0,
            themes_generated INTEGER NOT NULL,
            themes_preserved INTEGER NOT NULL,
            edges_decayed INTEGER NOT NULL,
            edges_pruned INTEGER NOT NULL,
            triangular_tensions_found INTEGER NOT NULL,
            inquiries_active INTEGER NOT NULL,
            report_json TEXT NOT NULL
        );
    """)

    # 4. Curriculum Modules & Timeline Milestones
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_milestones (
            module_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            concepts_count INTEGER NOT NULL,
            concept_slugs_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # 5. Curriculum Concepts Store
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_concepts (
            slug TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            module_id TEXT NOT NULL,
            module_title TEXT NOT NULL,
            summary TEXT,
            synthesis TEXT,
            citations_json TEXT NOT NULL DEFAULT '[]',
            prerequisites_json TEXT NOT NULL DEFAULT '[]',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_concepts_module ON curriculum_concepts(module_id);")
    
    return conn

