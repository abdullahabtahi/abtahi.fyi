import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Set, Tuple, Any
import networkx as nx

from app.schemas.feeds import (
    GraphSnapshot,
    IntellectualTension,
    EdgeType,
    EdgeDirection,
)

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

    def initialize(self, edges: list[tuple[str, str, dict]]):
        """
        Hydrate the graph with a list of edges.
        edges format: [(source_id, target_id, {"edge_type": ..., "plane": ...}), ...]
        """
        self.G.clear()
        for u, v, attrs in edges:
            self.G.add_edge(u, v, **attrs)
        self.precompute_metrics()

    def load_from_items(self, items: list[Any]):
        """
        Hydrate the graph directly from a collection of PublicItems or domain objects.
        """
        self.G.clear()
        for item in items:
            self.G.add_node(item.id, title=item.title, item_type=getattr(item, "item_type", "riff"), plane="public")
            for edge in getattr(item, "edges", []):
                self.G.add_edge(
                    edge.source_id,
                    edge.target_id,
                    edge_type=str(edge.edge_type),
                    reason=edge.reason,
                    confidence=edge.confidence,
                    plane="public"
                )
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
