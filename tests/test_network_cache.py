import pytest
import networkx as nx
from app.core.network import NetworkScienceCache

@pytest.fixture
def empty_cache():
    return NetworkScienceCache()

@pytest.fixture
def sample_edges():
    return [
        # Hub and spoke
        ("node_A", "hub", {"edge_type": "supports"}),
        ("node_B", "hub", {"edge_type": "challenges"}),
        ("node_C", "hub", {"edge_type": "supports"}),
        # Bridge
        ("hub", "bridge", {"edge_type": "related_to"}),
        ("bridge", "comm2_node1", {"edge_type": "related_to"}),
        # Community 2
        ("comm2_node1", "comm2_node2", {"edge_type": "supports"}),
        ("comm2_node2", "comm2_node3", {"edge_type": "supports"}),
        ("comm2_node3", "comm2_node1", {"edge_type": "supports"}),
    ]

@pytest.fixture
def populated_cache(sample_edges):
    cache = NetworkScienceCache()
    cache.initialize(sample_edges)
    return cache

def test_ego_graph_extraction(populated_cache):
    # Test 1-hop subgraph from node_A
    subgraph_1hop = populated_cache.extract_subgraph("node_A", radius=1)
    assert "node_A" in subgraph_1hop.nodes
    assert "hub" in subgraph_1hop.nodes
    assert "bridge" not in subgraph_1hop.nodes

    # Test 2-hop subgraph from node_A (should reach bridge and other hub spokes)
    subgraph_2hop = populated_cache.extract_subgraph("node_A", radius=2)
    assert "bridge" in subgraph_2hop.nodes
    assert "node_B" in subgraph_2hop.nodes # because node_A -> hub <- node_B is 2 undirected hops.
    # networkx ego_graph with undirected=True allows traversal against edge direction for neighborhoods.
    # We should ensure extract_subgraph treats the neighborhood as undirected for discovery purposes.

def test_incremental_edge_addition(empty_cache):
    assert len(empty_cache.G.nodes) == 0
    empty_cache.incremental_add("source_1", "target_1", {"edge_type": "supports"})
    assert "source_1" in empty_cache.G.nodes
    assert "target_1" in empty_cache.G.nodes
    assert empty_cache.G.has_edge("source_1", "target_1")

def test_pagerank_hubs(populated_cache):
    scores = populated_cache.get_pagerank()
    # "hub" should have a high pagerank because it has many incoming edges
    assert scores["hub"] > scores["node_A"]

def test_betweenness(populated_cache):
    scores = populated_cache.get_betweenness()
    # "bridge" connects the hub community to comm2
    # It should have a high betweenness centrality
    assert scores["bridge"] > 0
    assert scores["bridge"] > scores["node_A"]

def test_louvain(populated_cache):
    communities = populated_cache.get_communities()
    # Should detect at least two communities (the hub community and comm2)
    assert len(communities) >= 2
    
    # comm2 nodes should be in the same community
    comm2_group = None
    for c in communities:
        if "comm2_node1" in c:
            comm2_group = c
            break
            
    assert comm2_group is not None
    assert "comm2_node2" in comm2_group
    assert "comm2_node3" in comm2_group
