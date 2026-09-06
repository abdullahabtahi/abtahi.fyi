## 2025-01-01 - Instantiating MarkdownIt is slow
**Learning:** Instantiating `MarkdownIt` for every render can add a significant overhead (in benchmarks, creating it inside a loop was ~2.5x slower than reusing an instance).
**Action:** In `app/core/store.py`, `render_html` creates a new `MarkdownIt` instance on every call. We should cache this instance at the module level.
