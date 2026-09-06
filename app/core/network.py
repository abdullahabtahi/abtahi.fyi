import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Set, Tuple, Any
import networkx as nx

from app.schemas.feeds import (
    GraphSnapshot,
    IntellectualTension,
    EdgeType,
    EdgeDirection,
)
from app.schemas.synthesis import TriangularTensionRecord

class NetworkScienceCache:
    """
    In-memory NetworkX singleton for fast graph analytics, subgraph extraction,
    and sub-millisecond snapshot retrieval backed by SQLite.
    """
    
    def __init__(self):
        self.G = nx.DiGraph()
        self._pagerank_cache: dict[str, float] = {}
        self._betweenness_cache: dict[str, float] = {}
        self._communities_cache: list[set[str]] = []
        self._cached_snapshot: Optional[GraphSnapshot] = None
        self._curriculum_cache: dict[str, dict] = {}       # slug -> concept dict
        self._curriculum_modules: dict[str, dict] = {}     # module_id -> module dict
        self._connected_signals: dict[str, dict] = {}      # signal_id -> signal dict

    def initialize(self, edges: list[tuple[str, str, dict]]):
        """
        Hydrate the graph with a list of edges.
        edges format: [(source_id, target_id, {"edge_type": ..., "plane": ...}), ...]
        """
        self.G.clear()
        for u, v, attrs in edges:
            self.G.add_edge(u, v, **attrs)
        self._reapply_curriculum()
        self._reapply_signals()
        self.precompute_metrics()

    def _reapply_signals(self):
        """Re-applies all cached connected signals from Today review queue."""
        for sig_id, sig in self._connected_signals.items():
            node_id = f"signal-{sig.get('id', sig_id)}"
            self.G.add_node(
                node_id,
                title=sig.get("source_title") or sig.get("title", "Signal"),
                item_type="signal",
                node_type="signal",
                url=sig.get("source_url", ""),
                source_domain=sig.get("source_domain", ""),
                plane="shared",
            )
            concept_slug = sig.get("concept_slug")
            if concept_slug:
                edge_type = sig.get("edge_type", "example_of")
                self.G.add_edge(
                    node_id,
                    concept_slug,
                    edge_type=edge_type,
                    reason=sig.get("reviewed_citation") or f"{edge_type.replace('_', ' ').capitalize()} for {sig.get('concept_title', concept_slug)}",
                    confidence=1.0,
                    plane="shared",
                )

    def _reapply_curriculum(self):
        """Re-applies all cached curriculum concept nodes and edges with rich inter-connections."""
        for slug, concept in self._curriculum_cache.items():
            self.G.add_node(
                slug,
                title=concept.get("title", slug),
                item_type="concept",
                node_type="concept",
                module_id=concept.get("module_id", ""),
                module_title=concept.get("module_title", ""),
                summary=concept.get("summary", ""),
                plane="shared",
            )
            for prereq in concept.get("prerequisites", []):
                if prereq:
                    self.G.add_edge(
                        prereq,
                        slug,
                        edge_type="prerequisite_for",
                        reason=f"Prerequisite for {concept.get('title', slug)}",
                        confidence=1.0,
                        plane="shared",
                    )

        # 1. Re-apply sequential progressions within each module
        sorted_mod_ids = sorted(self._curriculum_modules.keys())
        for mod_id in sorted_mod_ids:
            mod_info = self._curriculum_modules[mod_id]
            slugs = mod_info.get("concept_slugs", [])
            for i in range(len(slugs) - 1):
                u, v = slugs[i], slugs[i + 1]
                if u and v and not self.G.has_edge(u, v):
                    self.G.add_edge(
                        u,
                        v,
                        edge_type="develops_into",
                        reason=f"Progression in {mod_info.get('title', mod_id)}",
                        confidence=1.0,
                        plane="shared",
                    )

        # 2. Inter-module progression bridges (connecting consecutive modules)
        for i in range(len(sorted_mod_ids) - 1):
            cur_mod = self._curriculum_modules[sorted_mod_ids[i]]
            next_mod = self._curriculum_modules[sorted_mod_ids[i + 1]]
            cur_slugs = cur_mod.get("concept_slugs", [])
            next_slugs = next_mod.get("concept_slugs", [])
            if cur_slugs and next_slugs:
                bridge_u = cur_slugs[-1]
                bridge_v = next_slugs[0]
                if bridge_u and bridge_v and not self.G.has_edge(bridge_u, bridge_v):
                    self.G.add_edge(
                        bridge_u,
                        bridge_v,
                        edge_type="develops_into",
                        reason=f"Curriculum progression from {cur_mod.get('title', sorted_mod_ids[i])} to {next_mod.get('title', sorted_mod_ids[i+1])}",
                        confidence=1.0,
                        plane="shared",
                    )

        # 3. Cross-connect concepts with public notes/links based on conceptual affinity
        for slug, concept in self._curriculum_cache.items():
            c_text = f"{concept.get('title', '')} {concept.get('summary', '')}".lower()
            for public_node, p_data in list(self.G.nodes(data=True)):
                if p_data.get("plane") == "public":
                    p_title = p_data.get("title", "").lower()
                    # Check thematic overlaps (e.g. system, architecture, failure, circuit, attention)
                    matches = [w for w in ["system", "architecture", "failure", "circuit", "attention", "benchmark", "resilience"] if w in c_text and w in p_title]
                    if matches and not self.G.has_edge(public_node, slug) and not self.G.has_edge(slug, public_node):
                        self.G.add_edge(
                            public_node,
                            slug,
                            edge_type="related_to",
                            reason=f"Shared conceptual foundation: {matches[0]}",
                            confidence=0.85,
                            plane="shared",
                        )

    def load_from_items(self, items: list[Any]):
        """
        Hydrate the graph directly from a collection of PublicItems or domain objects,
        preserving all active curriculum concept nodes and edges.
        """
        self.G.clear()
        for item in items:
            self.G.add_node(
                item.id,
                title=item.title,
                item_type=getattr(item, "item_type", "riff"),
                node_type=getattr(item, "item_type", "riff"),
                plane="public"
            )
            for edge in getattr(item, "edges", []):
                self.G.add_edge(
                    edge.source_id,
                    edge.target_id,
                    edge_type=str(edge.edge_type),
                    reason=edge.reason,
                    confidence=edge.confidence,
                    plane="public"
                )
        if not self._curriculum_cache or not self._connected_signals:
            try:
                from app.core.db import init_sqlite_db
                conn = init_sqlite_db()
                self.load_curriculum_from_db(conn)
                self.load_connected_signals_from_db(conn)
                conn.close()
            except Exception:
                pass
        self._reapply_curriculum()
        self._reapply_signals()
        self.precompute_metrics()


    def add_curriculum_module(self, module_id: str, module_title: str, concepts: list[Any]):
        """
        Adds concept nodes, prerequisite edges, and progression edges to the in-memory graph.
        """
        concept_slugs = []
        for concept in concepts:
            slug = getattr(concept, "slug", "") or (concept.get("slug", "") if isinstance(concept, dict) else "")
            title = getattr(concept, "title", slug) or (concept.get("title", slug) if isinstance(concept, dict) else slug)
            summary = getattr(concept, "summary", "") or (concept.get("summary", "") if isinstance(concept, dict) else "")
            prerequisites = getattr(concept, "prerequisites", []) or (concept.get("prerequisites", []) if isinstance(concept, dict) else [])

            concept_data = {
                "slug": slug,
                "title": title,
                "module_id": module_id,
                "module_title": module_title,
                "summary": summary,
                "prerequisites": list(prerequisites),
            }
            self._curriculum_cache[slug] = concept_data
            concept_slugs.append(slug)

            self.G.add_node(
                slug,
                title=title,
                item_type="concept",
                node_type="concept",
                module_id=module_id,
                module_title=module_title,
                summary=summary,
                plane="shared",
            )

            for prereq in prerequisites:
                if prereq:
                    self.G.add_edge(
                        prereq,
                        slug,
                        edge_type="prerequisite_for",
                        reason=f"Prerequisite for {title}",
                        confidence=1.0,
                        plane="shared",
                    )

        # Sequential links within the module
        for i in range(len(concept_slugs) - 1):
            u, v = concept_slugs[i], concept_slugs[i + 1]
            if u and v and not self.G.has_edge(u, v):
                self.G.add_edge(
                    u,
                    v,
                    edge_type="develops_into",
                    reason=f"Sequential progression in {module_title}",
                    confidence=1.0,
                    plane="shared",
                )

        self._curriculum_modules[module_id] = {
            "module_id": module_id,
            "title": module_title,
            "concept_slugs": concept_slugs,
        }

        self._cached_snapshot = None
        self.precompute_metrics()

    def load_curriculum_from_db(self, conn: sqlite3.Connection):
        """
        Loads persisted curriculum concepts and milestones from SQLite into the in-memory cache.
        """
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT slug, title, module_id, module_title, summary, prerequisites_json FROM curriculum_concepts")
            for slug, title, module_id, module_title, summary, prereqs_json in cursor.fetchall():
                try:
                    prereqs = json.loads(prereqs_json)
                except Exception:
                    prereqs = []
                self._curriculum_cache[slug] = {
                    "slug": slug,
                    "title": title,
                    "module_id": module_id,
                    "module_title": module_title,
                    "summary": summary or "",
                    "prerequisites": prereqs,
                }

            cursor.execute("SELECT module_id, title, concept_slugs_json FROM curriculum_milestones")
            for mod_id, title, slugs_json in cursor.fetchall():
                try:
                    slugs = json.loads(slugs_json)
                except Exception:
                    slugs = []
                self._curriculum_modules[mod_id] = {
                    "module_id": mod_id,
                    "title": title,
                    "concept_slugs": slugs,
                }

            self._reapply_curriculum()
            self.precompute_metrics()
        except sqlite3.OperationalError:
            # Tables may not be initialized yet
            pass

    def load_connected_signals_from_db(self, conn: sqlite3.Connection):
        """
        Loads persisted connected signals from SQLite into the in-memory cache.
        """
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, proposal_id, source_url, source_title, source_domain,
                       concept_slug, concept_title, edge_type, excerpt,
                       reviewed_citation, rationale, connected_at
                FROM connected_signals
                """
            )
            from app.core.firestore import resolve_article_url
            for row in cursor.fetchall():
                article_url = resolve_article_url(
                    source_domain=row[4] or "",
                    source_title=row[3] or "Signal",
                    explicit_url=row[2] or "",
                )
                sig = {
                    "id": row[0],
                    "proposal_id": row[1],
                    "source_url": article_url,
                    "source_title": row[3] or "Signal",
                    "source_domain": row[4] or "",
                    "concept_slug": row[5],
                    "concept_title": row[6] or row[5],
                    "edge_type": row[7] or "example_of",
                    "excerpt": row[8] or "",
                    "reviewed_citation": row[9] or "",
                    "rationale": row[10] or "",
                    "connected_at": row[11] or "",
                }
                self._connected_signals[row[0]] = sig
            self._reapply_signals()
            self.precompute_metrics()
        except sqlite3.OperationalError:
            pass

    def add_connected_signal(self, sig: dict):
        """
        Dynamically add an approved signal into the in-memory graph and update metrics.
        """
        sig_id = str(sig.get("id") or sig.get("proposal_id") or "")
        if sig_id:
            self._connected_signals[sig_id] = sig
            self._reapply_signals()
            self._cached_snapshot = None
            self.precompute_metrics()

    def add_connected_signals(self, signals: list[dict]):
        """
        Dynamically add multiple signals into the in-memory graph.
        """
        for sig in signals:
            sig_id = str(sig.get("id") or sig.get("proposal_id") or "")
            if sig_id:
                self._connected_signals[sig_id] = sig
        self._reapply_signals()
        self._cached_snapshot = None
        self.precompute_metrics()

    def incremental_add(self, source_id: str, target_id: str, attributes: dict):
        """
        Safe incremental mutation when a new connection is approved.
        """
        self.G.add_edge(source_id, target_id, **attributes)
        self._cached_snapshot = None

    def extract_subgraph(self, center_id: str, radius: int = 2) -> nx.DiGraph:
        """
        Extracts 1-2 hop neighborhood around center_id.
        """
        if center_id not in self.G.nodes:
            return nx.DiGraph()
            
        subgraph = nx.ego_graph(self.G, center_id, radius=radius, undirected=True)
        return subgraph

    def get_item_edges(self, item_id: str) -> dict[str, list[dict]]:
        """
        Extracts incoming and outgoing edges for item_id with metadata.
        """
        outgoing = []
        incoming = []

        if item_id in self.G:
            for _, target, data in self.G.out_edges(item_id, data=True):
                target_node = self.G.nodes.get(target, {})
                outgoing.append({
                    "target_id": target,
                    "target_title": target_node.get("title", target),
                    "edge_type": data.get("edge_type", "related_to"),
                    "reason": data.get("reason", ""),
                    "confidence": data.get("confidence", 1.0),
                    "direction": "outgoing",
                })

            for source, _, data in self.G.in_edges(item_id, data=True):
                source_node = self.G.nodes.get(source, {})
                incoming.append({
                    "source_id": source,
                    "source_title": source_node.get("title", source),
                    "edge_type": data.get("edge_type", "related_to"),
                    "reason": data.get("reason", ""),
                    "confidence": data.get("confidence", 1.0),
                    "direction": "incoming",
                })

        return {
            "outgoing": outgoing,
            "incoming": incoming,
        }

    def precompute_metrics(self):
        """
        Precomputes all graph metrics and refreshes the in-memory GraphSnapshot.
        """
        self._pagerank_cache = self._compute_pagerank()
        self._betweenness_cache = self._compute_betweenness()
        self._communities_cache = self._compute_communities()
        self._cached_snapshot = self._build_snapshot()

    def get_pagerank(self) -> dict[str, float]:
        """O(1) read for PageRank scores"""
        return self._pagerank_cache
        
    def get_betweenness(self) -> dict[str, float]:
        """O(1) read for Betweenness Centrality scores"""
        return self._betweenness_cache
        
    def get_communities(self) -> list[set[str]]:
        """O(1) read for Louvain communities"""
        return self._communities_cache

    def get_snapshot(self) -> GraphSnapshot:
        """O(1) read for cached GraphSnapshot"""
        if self._cached_snapshot is None:
            self.precompute_metrics()
        return self._cached_snapshot

    def _compute_pagerank(self, alpha=0.85, max_iter=100, tol=1.0e-6) -> dict[str, float]:
        if not self.G:
            return {}
        
        N = len(self.G)
        pr = {node: 1.0 / N for node in self.G}
        out_degree = {node: self.G.out_degree(node) for node in self.G}
        dangling_nodes = [node for node in self.G if out_degree[node] == 0]
        
        for _ in range(max_iter):
            prev_pr = pr.copy()
            dangling_sum = sum(prev_pr[node] for node in dangling_nodes)
            base = (1.0 - alpha) / N + alpha * dangling_sum / N
            pr = {node: base for node in self.G}
            
            for node in self.G:
                if out_degree[node] > 0:
                    share = alpha * prev_pr[node] / out_degree[node]
                    for neighbor in self.G.successors(node):
                        pr[neighbor] += share
            
            err = sum(abs(pr[node] - prev_pr[node]) for node in pr)
            if err < N * tol:
                return pr
                
        return pr

    def _compute_betweenness(self) -> dict[str, float]:
        if not self.G:
            return {}
        return nx.betweenness_centrality(self.G)

    def compute_cluster_hash(self, member_ids: list[str] | set[str]) -> str:
        """
        Computes a deterministic 12-char SHA-256 cluster hash for a set of member IDs.
        """
        sorted_ids = sorted(list(member_ids))
        hasher = hashlib.sha256()
        for mid in sorted_ids:
            hasher.update(mid.encode("utf-8"))
            node_data = self.G.nodes.get(mid, {})
            hasher.update(str(node_data.get("title", "")).encode("utf-8"))
        return hasher.hexdigest()[:12]

    def extract_louvain_communities(self, min_size: int = 3, seed: int = 42) -> list[dict]:
        """
        Detects Louvain communities on the undirected projection of self.G.
        Filters for communities with size >= min_size (default 3).
        Returns list of dicts with community_id, size, members (sorted), and cluster_hash.
        """
        if not self.G or len(self.G) < min_size:
            return []

        G_un = self.G.to_undirected()
        G_un.remove_edges_from(nx.selfloop_edges(G_un))
        
        try:
            raw_communities = nx.community.louvain_communities(G_un, seed=seed)
        except Exception:
            return []

        valid_communities = []
        for idx, comm in enumerate(raw_communities):
            if len(comm) >= min_size:
                members = sorted(list(comm))
                c_hash = self.compute_cluster_hash(members)
                valid_communities.append({
                    "community_id": idx,
                    "size": len(members),
                    "members": members,
                    "cluster_hash": c_hash,
                })
        return valid_communities

    def _compute_communities(self) -> list[set[str]]:
        if not self.G:
            return []
        
        G_un = self.G.to_undirected()
        G_un.remove_edges_from(nx.selfloop_edges(G_un))
        communities = nx.community.louvain_communities(G_un)
        return list(communities)

    def extract_intellectual_tensions(self) -> list[IntellectualTension]:
        """
        Finds all explicit 'challenges' edges and triangular contradictions.
        """
        tensions: list[IntellectualTension] = []
        for u, v, data in self.G.edges(data=True):
            edge_type = str(data.get("edge_type", "")).lower()
            if edge_type in ("challenges", EdgeType.CHALLENGES.value):
                source_node = self.G.nodes.get(u, {})
                target_node = self.G.nodes.get(v, {})
                
                # Check for triangular loop (e.g. u -> v challenges, but both connect to w)
                triangular_loop = None
                common_neighbors = list(set(self.G.successors(u)).intersection(set(self.G.successors(v))))
                if common_neighbors:
                    triangular_loop = (u, v, common_neighbors[0])

                tensions.append(
                    IntellectualTension(
                        source_id=u,
                        source_title=source_node.get("title", u),
                        target_id=v,
                        target_title=target_node.get("title", v),
                        challenge_quote=data.get("challenge_quote", ""),
                        reason=data.get("reason", "Intellectual contradiction or methodological disagreement."),
                        triangular_loop=triangular_loop,
                    )
                )
        return tensions

    def calculate_edge_decay(self, as_of_date: datetime | None = None) -> list[dict]:
        """
        Calculates temporal confidence decay for active edges:
        - Edges older than 90 days without citations decay:
          - 5% standard (conf * 0.95)
          - 2.5% for challenges (conf * 0.975)
          - 0% for superseded_by (permanently exempt)
        - Edges below 0.30 are marked for pruning (is_pruned = True)
        """
        now = as_of_date or datetime.now(timezone.utc)
        results = []

        for u, v, data in self.G.edges(data=True):
            edge_type = str(data.get("edge_type", "related_to"))
            conf = float(data.get("confidence", 1.0))

            if edge_type == "superseded_by":
                results.append({
                    "source": u,
                    "target": v,
                    "edge_type": edge_type,
                    "old_confidence": conf,
                    "new_confidence": conf,
                    "is_pruned": False,
                    "created_at": data.get("created_at"),
                    "last_reinforced_at": data.get("last_reinforced_at"),
                })
                continue

            last_ts_raw = data.get("last_reinforced_at") or data.get("created_at")
            if last_ts_raw:
                if isinstance(last_ts_raw, str):
                    try:
                        last_ts = datetime.fromisoformat(last_ts_raw.replace("Z", "+00:00"))
                    except Exception:
                        last_ts = now
                elif isinstance(last_ts_raw, datetime):
                    last_ts = last_ts_raw
                else:
                    last_ts = now
            else:
                last_ts = now

            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)

            age_days = (now - last_ts).days
            if age_days > 90:
                if edge_type in ("challenges", "contradicts"):
                    new_conf = round(max(0.0, conf * 0.975), 4)
                else:
                    new_conf = round(max(0.0, conf * 0.95), 4)
            else:
                new_conf = conf

            is_pruned = new_conf < 0.30
            results.append({
                "source": u,
                "target": v,
                "edge_type": edge_type,
                "old_confidence": conf,
                "new_confidence": new_conf,
                "is_pruned": is_pruned,
                "created_at": data.get("created_at"),
                "last_reinforced_at": data.get("last_reinforced_at"),
            })

        return results

    def detect_triangular_contradictions(self) -> list[TriangularTensionRecord]:
        """
        Identifies length-3 directed cycles (A -> B -> C -> A) containing at least
        one 'challenges' edge and at least one 'supports' or 'develops_into' edge.
        """
        triads: list[TriangularTensionRecord] = []
        if not self.G or len(self.G) < 3:
            return triads

        seen_triads: set[frozenset[str]] = set()

        try:
            cycles = nx.simple_cycles(self.G, length_bound=3)
        except TypeError:
            cycles = [c for c in nx.simple_cycles(self.G) if len(c) == 3]

        for cycle in cycles:
            if len(cycle) != 3:
                continue

            a, b, c = cycle[0], cycle[1], cycle[2]
            key = frozenset([a, b, c])
            if key in seen_triads:
                continue
            seen_triads.add(key)

            e_ab = self.G[a][b].get("edge_type", "related_to")
            e_bc = self.G[b][c].get("edge_type", "related_to")
            e_ca = self.G[c][a].get("edge_type", "related_to")
            types = [e_ab, e_bc, e_ca]

            if "challenges" in types and any(t in ("supports", "develops_into") for t in types):
                node_a_title = self.G.nodes.get(a, {}).get("title", a)
                node_b_title = self.G.nodes.get(b, {}).get("title", b)
                node_c_title = self.G.nodes.get(c, {}).get("title", c)

                triad_id = f"triad-{hashlib.sha256(f'{sorted([a, b, c])}'.encode()).hexdigest()[:8]}"
                summary = f"Dialectical contradiction cycle between {node_a_title}, {node_b_title}, and {node_c_title}."
                triads.append(
                    TriangularTensionRecord(
                        triad_id=triad_id,
                        node_a=a,
                        node_b=b,
                        node_c=c,
                        edge_ab_type=e_ab,
                        edge_bc_type=e_bc,
                        edge_ca_type=e_ca,
                        contradiction_summary=summary,
                        confidence=0.88,
                        detected_at=datetime.now(timezone.utc),
                    )
                )

        return triads

    def find_frontier_concepts(self, pagerank_percentile: float = 0.75, max_supports: int = 2) -> list[dict]:
        """
        Identifies concepts on the graph perimeter with high PageRank authority
        (>= 75th percentile) but lacking empirical grounding (< 2 supports in-degree).
        """
        if not self.G:
            return []

        pr = self.get_pagerank() or self._compute_pagerank()
        if not pr:
            return []

        scores = sorted(pr.values())
        cutoff_idx = int(len(scores) * pagerank_percentile)
        threshold = scores[min(cutoff_idx, len(scores) - 1)] if scores else 0.0

        frontier = []
        for node, score in sorted(pr.items(), key=lambda x: x[1], reverse=True):
            if score < threshold:
                continue

            supports_in = 0
            for _, _, data in self.G.in_edges(node, data=True):
                if data.get("edge_type") in ("supports", "application_of", "example_of"):
                    supports_in += 1

            if supports_in < max_supports:
                node_data = self.G.nodes.get(node, {})
                frontier.append({
                    "id": node,
                    "title": node_data.get("title", node),
                    "summary": node_data.get("summary", ""),
                    "pagerank": round(score, 4),
                    "supports_in": supports_in,
                })

        return frontier

    def _build_snapshot(self) -> GraphSnapshot:
        """
        Builds an immutable GraphSnapshot domain object.
        """
        now = datetime.now(timezone.utc)
        total_items = len(self.G)
        total_edges = self.G.number_of_edges()

        # Top connected nodes
        pr = self._pagerank_cache or self._compute_pagerank()
        ranked = sorted(
            [
                {
                    "id": node,
                    "title": self.G.nodes.get(node, {}).get("title", node),
                    "pagerank": round(pr.get(node, 0.0), 4),
                    "degree": self.G.degree(node),
                    "in_degree": self.G.in_degree(node),
                    "out_degree": self.G.out_degree(node),
                }
                for node in self.G.nodes
            ],
            key=lambda x: x["pagerank"],
            reverse=True,
        )

        tensions = tuple(self.extract_intellectual_tensions())

        # Community groups
        communities_data = []
        for idx, comm in enumerate(self._communities_cache or []):
            members = list(comm)
            communities_data.append({
                "community_id": idx,
                "size": len(members),
                "members": members,
            })

        # Edge type distribution
        distribution: dict[str, int] = {}
        for _, _, data in self.G.edges(data=True):
            etype = str(data.get("edge_type", "related_to"))
            distribution[etype] = distribution.get(etype, 0) + 1

        return GraphSnapshot(
            generated_at=now,
            total_items=total_items,
            total_edges=total_edges,
            top_connected=tuple(ranked[:20]),
            tensions=tensions,
            communities=tuple(communities_data),
            edge_type_distribution=distribution,
        )

    def save_snapshot_to_db(self, conn: sqlite3.Connection, key: str = "default"):
        """
        Persists current snapshot into SQLite table public_graph_snapshot.
        """
        snapshot = self.get_snapshot()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO public_graph_snapshot (snapshot_key, snapshot_json, generated_at)
            VALUES (?, ?, ?);
            """,
            (key, snapshot.model_dump_json(), snapshot.generated_at.isoformat()),
        )
        conn.commit()

    def load_snapshot_from_db(self, conn: sqlite3.Connection, key: str = "default") -> bool:
        """
        Loads pre-computed snapshot from SQLite on cold boot in <1ms.
        """
        cursor = conn.cursor()
        cursor.execute(
            "SELECT snapshot_json FROM public_graph_snapshot WHERE snapshot_key = ? LIMIT 1;",
            (key,),
        )
        row = cursor.fetchone()
        if row:
            try:
                self._cached_snapshot = GraphSnapshot.model_validate_json(row[0])
                return True
            except Exception:
                return False
        return False

# Global singleton instance
network_cache = NetworkScienceCache()
