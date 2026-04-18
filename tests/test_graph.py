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
        # threshold=0.95 excludes semantic edges (similarity=0.9 from distance=0.1)
        G = build_graph(threshold=0.95)

    assert G.has_edge("note_projects_ytk", "note_projects_epicmap") or \
           G.has_edge("note_projects_epicmap", "note_projects_ytk")
    edge_data = (G["note_projects_ytk"].get("note_projects_epicmap") or
                 G["note_projects_epicmap"].get("note_projects_ytk") or {})
    assert edge_data.get("type") == "EXTRACTED"
    assert edge_data.get("weight") == 1.0


def test_build_graph_semantic_edge_below_threshold():
    """Pairs below threshold get no semantic edge; pairs above threshold do."""
    from ytk.graph import build_graph

    no_tag_docs = [
        {
            "id": "note_a",
            "document": "doc a",
            "metadata": {"doc_id": "note_a", "tags": "tag-a", "source_path": "/vault/a.md"},
        },
        {
            "id": "note_b",
            "document": "doc b",
            "metadata": {"doc_id": "note_b", "tags": "tag-b", "source_path": "/vault/b.md"},
        },
    ]

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(no_tag_docs)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])), \
         patch("ytk.graph._read_note_concepts", return_value=[]):
        # distance=0.1 -> similarity=0.9. threshold=0.95 means 0.9 < 0.95 -> no edge
        G_strict = build_graph(threshold=0.95)
        # threshold=0.5 means 0.9 >= 0.5 -> edge exists
        G_loose = build_graph(threshold=0.5)

    assert not G_strict.has_edge("note_a", "note_b"), "similarity 0.9 should be below threshold 0.95"
    assert G_loose.has_edge("note_a", "note_b"), "similarity 0.9 should be above threshold 0.5"


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


def test_build_graph_concept_edge(tmp_path):
    """Two notes sharing a key concept get an EXTRACTED edge with weight 0.9."""
    import networkx as nx
    from ytk.graph import build_graph

    # Create real note files with a shared concept
    note_a = tmp_path / "note_a.md"
    note_b = tmp_path / "note_b.md"
    note_a.write_text(
        "---\ntitle: A\ntags: tag-a\n---\n## Key Concepts\n- chromadb: vector store\n",
        encoding="utf-8",
    )
    note_b.write_text(
        "---\ntitle: B\ntags: tag-b\n---\n## Key Concepts\n- chromadb: search backend\n",
        encoding="utf-8",
    )

    docs = [
        {
            "id": "note_a",
            "document": "doc a",
            "metadata": {"doc_id": "note_a", "tags": "tag-a", "source_path": str(note_a)},
        },
        {
            "id": "note_b",
            "document": "doc b",
            "metadata": {"doc_id": "note_b", "tags": "tag-b", "source_path": str(note_b)},
        },
    ]

    with patch("ytk.graph._memories_collection", return_value=_mock_collection(docs)), \
         patch("ytk.graph._videos_collection", return_value=_mock_collection([])):
        # threshold=0.95 to exclude semantic edges (distance=0.1 -> similarity=0.9 < 0.95)
        G = build_graph(threshold=0.95)

    assert G.has_edge("note_a", "note_b") or G.has_edge("note_b", "note_a"), \
        "notes sharing 'chromadb' concept should have an edge"
    edge_data = G["note_a"].get("note_b") or G["note_b"].get("note_a") or {}
    assert edge_data.get("type") == "EXTRACTED"
    assert abs(edge_data.get("weight", 0) - 0.9) < 0.01


def test_export_json(tmp_path):
    """export_json writes a valid JSON file with nodes and edges."""
    import networkx as nx
    from ytk.graph import export_json

    G = nx.Graph()
    G.add_node("a", title="Note A", url="https://example.com", note_type="memory", tags="ai", community=0)
    G.add_node("b", title="Note B", url="https://youtube.com", note_type="video", tags="ai", community=0)
    G.add_edge("a", "b", weight=0.9, type="EXTRACTED", label="tag:ai")

    out = tmp_path / "graph.json"
    export_json(G, out)

    import json as _json
    data = _json.loads(out.read_text())
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["nodes"][0]["id"] in {"a", "b"}


def test_export_html(tmp_path):
    """export_html writes a self-contained HTML file with vis.js."""
    import networkx as nx
    from ytk.graph import export_html

    G = nx.Graph()
    G.add_node("a", title="Note A", url="https://example.com", note_type="memory", tags="ai", community=0)

    out = tmp_path / "graph.html"
    export_html(G, out)

    html = out.read_text()
    assert "vis-network" in html
    assert "Note A" in html
    assert "<script" in html
