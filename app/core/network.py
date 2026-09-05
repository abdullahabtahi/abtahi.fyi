import networkx as nx

class NetworkScienceCache:
    """
    In-memory NetworkX singleton for fast graph analytics and subgraph extraction.
    Hydrated from the primary SQLite store on startup.
    """
    
    def __init__(self):
        self.G = nx.DiGraph()
        self._pagerank_cache: dict[str, float] = {}
        self._betweenness_cache: dict[str, float] = {}
        self._communities_cache: list[set[str]] = []

    def initialize(self, edges: list[tuple[str, str, dict]]):
        """
        Hydrate the graph with a list of edges.
        edges format: [(source_id, target_id, {"edge_type": ...}), ...]
        """
        self.G.clear()
        self.G.add_edges_from(edges)
        self.precompute_metrics()

    def incremental_add(self, source_id: str, target_id: str, attributes: dict):
        """
        Safe incremental mutation when a new connection is approved.
        """
        self.G.add_edge(source_id, target_id, **attributes)
        # Note: In a production setting with frequent mutations, you would only call
        # precompute_metrics() on a schedule (e.g., Nightly Synthesis) to maintain 
        # UI responsiveness, as defined in the Cache Contract.

    def extract_subgraph(self, center_id: str, radius: int = 2) -> nx.DiGraph:
        """
        Extracts 1-2 hop neighborhood.
        Uses undirected ego_graph to traverse incoming and outgoing edges,
        but returns a directed subgraph containing those nodes.
        """
        if center_id not in self.G.nodes:
            return nx.DiGraph()
            
        subgraph = nx.ego_graph(self.G, center_id, radius=radius, undirected=True)
        return subgraph

    def precompute_metrics(self):
        """
        Precompute all metrics to satisfy the O(1) read Cache Contract.
        Runs exclusively during: Cold boot, Nightly Synthesis, Admin mutation.
        """
        self._pagerank_cache = self._compute_pagerank()
        self._betweenness_cache = self._compute_betweenness()
        self._communities_cache = self._compute_communities()

    def get_pagerank(self) -> dict[str, float]:
        """O(1) read for PageRank scores"""
        return self._pagerank_cache
        
    def get_betweenness(self) -> dict[str, float]:
        """O(1) read for Betweenness Centrality scores"""
        return self._betweenness_cache
        
    def get_communities(self) -> list[set[str]]:
        """O(1) read for Louvain communities"""
        return self._communities_cache

    def _compute_pagerank(self, alpha=0.85, max_iter=100, tol=1.0e-6) -> dict[str, float]:
        """
        Calculate PageRank scores for all nodes.
        Implemented in pure Python to avoid numpy/scipy C-extension dependencies.
        """
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

# Global singleton instance
network_cache = NetworkScienceCache()
