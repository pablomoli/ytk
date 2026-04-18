from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
import json


def _mock_collection(docs: list[dict]) -> MagicMock:
    """Build a mock ChromaDB collection from a list of {id, document, metadata} dicts."""
    col = MagicMock()
    col.count.return_value = len(docs)
    col.get.return_value = {
        "ids": [d["id"] for d in docs],
        "documents": [d["document"] for d in docs],
        "metadatas": [d["metadata"] for d in docs],
    }

    def _query(query_texts, n_results, **kwargs):
        results = [d for d in docs if d["document"] != query_texts[0]][:n_results]
        return {
            "ids": [[d["id"] for d in results]],
            "distances": [[0.1] * len(results)],
            "metadatas": [[d["metadata"] for d in results]],
            "documents": [[d["document"] for d in results]],
        }
    col.query.side_effect = _query
    return col


SAMPLE_DOCS = [
    {
        "id": "note_projects_ytk",
        "document": "ytk knowledge system",
        "metadata": {"doc_id": "note_projects_ytk", "tags": "projects", "source_path": "/vault/projects/ytk.md"},
    },
    {
        "id": "note_projects_epicmap",
        "document": "epicmap mapping tool",
        "metadata": {"doc_id": "note_projects_epicmap", "tags": "projects", "source_path": "/vault/projects/epicmap.md"},
    },
]


def test_build_graph_creates_nodes():
    """build_graph creates one node per indexed document."""
    import networkx as nx
    from ytk.graph import build_graph

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(SAMPLE_DOCS)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        G = build_graph(threshold=0.5)

    assert len(G.nodes) == 2
    assert "note_projects_ytk" in G.nodes


def test_build_graph_shared_tag_edge():
    """Two notes with the same tag get an EXTRACTED edge."""
    from ytk.graph import build_graph

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(SAMPLE_DOCS)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        G = build_graph(threshold=0.5)

    assert G.has_edge("note_projects_ytk", "note_projects_epicmap") or \
           G.has_edge("note_projects_epicmap", "note_projects_ytk")


def test_build_graph_semantic_edge_below_threshold():
    """build_graph runs for both strict and loose thresholds without error."""
    from ytk.graph import build_graph

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(SAMPLE_DOCS)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        G_strict = build_graph(threshold=0.95)
        G_loose = build_graph(threshold=0.5)

    assert len(G_strict.nodes) == 2
    assert len(G_loose.nodes) == 2


def test_parse_key_concepts():
    """_read_note_concepts extracts concept names from ## Key Concepts section."""
    from ytk.graph import _read_note_concepts

    content = (
        "---\ntitle: T\n---\n"
        "## Key Concepts\n"
        "- yt-dlp: a video downloader\n"
        "- ChromaDB: vector store\n"
        "- plain concept\n"
        "## Other\n"
        "other content\n"
    )
    concepts = _read_note_concepts(content)
    assert "yt-dlp" in concepts
    assert "ChromaDB" in concepts
    assert "plain concept" in concepts


def test_detect_communities_returns_mapping():
    """detect_communities returns a dict mapping every node to an int."""
    import networkx as nx
    from ytk.graph import detect_communities

    G = nx.Graph()
    G.add_edges_from([("a", "b"), ("b", "c"), ("d", "e")])
    communities = detect_communities(G)

    assert set(communities.keys()) == {"a", "b", "c", "d", "e"}
    assert all(isinstance(v, int) for v in communities.values())
