import sqlite3
import pytest
from app.core.db import init_sqlite_db

def test_sqlite_wal_pragma(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_sqlite_db(str(db_path))
    
    # Check WAL
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    assert cursor.fetchone()[0].lower() == "wal"
    
    # Check cache_size
    cursor.execute("PRAGMA cache_size;")
    assert cursor.fetchone()[0] == -64000
    
    # Check synchronous
    cursor.execute("PRAGMA synchronous;")
    # Normal is typically 1
    assert cursor.fetchone()[0] in (1, "NORMAL")
    
    conn.close()

def test_vec_tables_exist(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_sqlite_db(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    assert "vec_items" in tables
    assert "vec_concepts" in tables
    assert "vec_chunks" in tables
    
    conn.close()

def test_cosine_distance_k5(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_sqlite_db(str(db_path))
    cursor = conn.cursor()
    
    # Insert mock vectors. SQLite-vec expects vectors to be inserted via json or bytes.
    # In sqlite-vec 0.1.6, we can just insert a JSON array of floats.
    mock_vectors = [
        ("c1", "[1.0, 0.0, 0.0]"),
        ("c2", "[0.9, 0.1, 0.0]"),
        ("c3", "[0.0, 1.0, 0.0]"),
        ("c4", "[0.8, 0.2, 0.0]"),
        ("c5", "[0.7, 0.3, 0.0]"),
        ("c6", "[0.1, 0.9, 0.0]")
    ]
    
    # Since they must be 768 dims, let's pad them up to 768
    def pad(vec):
        import json
        v = json.loads(vec)
        v.extend([0.0] * (768 - len(v)))
        return json.dumps(v)
    
    for c_id, vec in mock_vectors:
        cursor.execute("INSERT INTO vec_concepts(concept_id, embedding) VALUES (?, ?)", (c_id, pad(vec)))
    
    conn.commit()
    
    # Query nearest to [1.0, 0.0, ... 0.0]
    query_vec = pad("[1.0, 0.0, 0.0]")
    
    cursor.execute("""
        SELECT concept_id 
        FROM vec_concepts 
        WHERE embedding MATCH ? 
        AND k = 5
    """, (query_vec,))
    
    results = [row[0] for row in cursor.fetchall()]
    assert len(results) == 5
    assert results == ["c1", "c2", "c4", "c5", "c6"] or results == ["c1", "c2", "c4", "c5", "c3"] # Actually distance is smallest first
    
    # "c1" is identical (dist=0)
    # "c2" is dist to [0.9, 0.1]
    # "c4" is dist to [0.8, 0.2]
    # "c5" is dist to [0.7, 0.3]
    # "c3" is [0.0, 1.0] -> dist=1
    # "c6" is [0.1, 0.9] -> dist to 1.0 is higher than others.
    
    assert results[0] == "c1"
    
    conn.close()
