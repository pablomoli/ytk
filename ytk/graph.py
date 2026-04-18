"""Knowledge graph builder: vault notes as nodes, edges from tags/concepts/semantics."""

from __future__ import annotations

import json
import re
from pathlib import Path

import networkx as nx

_PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]


def _memories_collection():
    from .store import _memories_collection as _mc
    return _mc()


def _videos_collection():
    from .store import _videos_collection as _vc
    return _vc()


def _read_note_concepts(content: str) -> list[str]:
    """Extract concept names from the ## Key Concepts section of a vault note."""
    m = re.search(r"^## Key Concepts\n(.*?)(?=^##|\Z)", content, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    return re.findall(r"^- ([^:\n]+?)(?:\s*:.*)?$", section, re.MULTILINE)


def build_graph(threshold: float = 0.75) -> nx.Graph:
    """
    Build a NetworkX graph from all indexed vault notes.

    Nodes: one per indexed document (memories + videos collections).
    Edges:
      - Shared interest_tags (weight=1.0, type=EXTRACTED)
      - Shared key_concept terms (weight=0.9, type=EXTRACTED)
      - ChromaDB semantic similarity >= threshold (weight=similarity, type=INFERRED)
    """
    G = nx.Graph()

    all_docs: list[dict] = []

    mem_col = _memories_collection()
    if mem_col.count() > 0:
        result = mem_col.get()
        for doc_id, doc_text, meta in zip(
            result["ids"], result["documents"], result["metadatas"]
        ):
            all_docs.append({
                "id": doc_id,
                "text": doc_text,
                "meta": meta,
                "collection": "memory",
            })

    vid_col = _videos_collection()
    if vid_col.count() > 0:
        result = vid_col.get()
        for doc_id, doc_text, meta in zip(
            result["ids"], result["documents"], result["metadatas"]
        ):
            all_docs.append({
                "id": doc_id,
                "text": doc_text,
                "meta": meta,
                "collection": "video",
            })

    if not all_docs:
        return G

    for doc in all_docs:
        meta = doc["meta"]
        source_path = meta.get("source_path", "")
        note_type = _infer_type(source_path, doc["collection"])
        G.add_node(
            doc["id"],
            title=meta.get("title", doc["id"]),
            url=meta.get("url", source_path),
            note_type=note_type,
            tags=meta.get("tags", ""),
            source_path=source_path,
            community=0,
        )

    # Tag edges
    by_tag: dict[str, list[str]] = {}
    for doc in all_docs:
        for tag in [t.strip() for t in doc["meta"].get("tags", "").split(",") if t.strip()]:
            by_tag.setdefault(tag, []).append(doc["id"])
    for tag, node_ids in by_tag.items():
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                _add_or_upgrade_edge(G, node_ids[i], node_ids[j], 1.0, "EXTRACTED", f"tag:{tag}")

    # Concept edges
    concepts_by_node: dict[str, list[str]] = {}
    for doc in all_docs:
        sp = doc["meta"].get("source_path", "")
        if sp and Path(sp).exists():
            content = Path(sp).read_text(encoding="utf-8", errors="replace")
            concepts_by_node[doc["id"]] = _read_note_concepts(content)

    by_concept: dict[str, list[str]] = {}
    for node_id, concepts in concepts_by_node.items():
        for concept in concepts:
            key = concept.lower().strip()
            by_concept.setdefault(key, []).append(node_id)
    for concept, node_ids in by_concept.items():
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                _add_or_upgrade_edge(G, node_ids[i], node_ids[j], 0.9, "EXTRACTED", f"concept:{concept}")

    # Semantic edges — queried within each collection only (cross-collection pairs
    # are covered by tag/concept edges; cross-collection ChromaDB queries would
    # require a combined collection or separate query+merge step)
    all_ids = {doc["id"] for doc in all_docs}
    for doc in all_docs:
        try:
            col = mem_col if doc["collection"] == "memory" else vid_col
            n_results = min(10, col.count())
            if n_results < 2:
                continue
            results = col.query(query_texts=[doc["text"]], n_results=n_results)
            for neighbor_id, distance in zip(results["ids"][0], results["distances"][0]):
                if neighbor_id == doc["id"] or neighbor_id not in all_ids:
                    continue
                similarity = 1.0 - distance
                if similarity >= threshold:
                    _add_or_upgrade_edge(G, doc["id"], neighbor_id, similarity, "INFERRED", "semantic")
        except Exception as exc:
            import sys
            print(f"[ytk] semantic edge query failed for {doc['id']!r}: {exc}", file=sys.stderr)
            continue

    return G


def _infer_type(source_path: str, collection: str) -> str:
    if collection == "video" or "sources/youtube" in source_path:
        return "video"
    if "sources/web" in source_path:
        return "web"
    return "memory"


def _add_or_upgrade_edge(
    G: nx.Graph, a: str, b: str, weight: float, edge_type: str, label: str
) -> None:
    """Add edge or upgrade to higher-confidence type if edge already exists."""
    if G.has_edge(a, b):
        if weight > G[a][b].get("weight", 0):
            G[a][b].update({"weight": weight, "type": edge_type, "label": label})
    else:
        G.add_edge(a, b, weight=weight, type=edge_type, label=label)


def detect_communities(G: nx.Graph) -> dict:
    """Assign community IDs to all nodes. Returns {node_id: community_int}."""
    if len(G.nodes) == 0:
        return {}
    try:
        import graspologic
        from graspologic.partition import leiden
        # leiden returns Dict[node, int] directly
        communities_list = leiden(G)
        mapping = dict(communities_list)
        # Assign isolated nodes (omitted by leiden) their own community IDs
        next_id = max(mapping.values(), default=-1) + 1
        for node in G.nodes:
            if node not in mapping:
                mapping[node] = next_id
                next_id += 1
        return mapping
    except (ImportError, Exception):
        from networkx.algorithms.community import greedy_modularity_communities
        communities_list = list(greedy_modularity_communities(G))
        mapping = {}
        for i, community in enumerate(communities_list):
            for node in community:
                mapping[node] = i
        # Assign isolated nodes (omitted by greedy_modularity_communities) their own community IDs
        next_id = max(mapping.values(), default=-1) + 1
        for node in G.nodes:
            if node not in mapping:
                mapping[node] = next_id
                next_id += 1
        return mapping


_VIS_CDN = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<title>ytk knowledge graph</title>
<script src="{vis_cdn}"></script>
<style>
  body {{ margin: 0; background: #1a1a2e; font-family: monospace; }}
  #graph {{ width: 100vw; height: 100vh; }}
  #info {{ position: fixed; top: 12px; right: 16px; color: #aaa; font-size: 12px; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="info">{node_count} nodes &middot; {edge_count} edges &middot; {community_count} communities</div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});
var network = new vis.Network(
  document.getElementById("graph"),
  {{ nodes: nodes, edges: edges }},
  {{
    nodes: {{ shape: "dot", scaling: {{ min: 8, max: 30 }}, font: {{ color: "#eee" }} }},
    edges: {{ smooth: false }},
    physics: {{ stabilization: {{ iterations: 200 }} }}
  }}
);
network.on("click", function(p) {{
  if (p.nodes.length > 0) {{
    var n = nodes.get(p.nodes[0]);
    if (n && n.url) window.open(n.url, "_blank");
  }}
}});
</script>
</body>
</html>"""

_EDGE_COLORS = {"EXTRACTED": "#4e79a7", "INFERRED": "#888"}


def export_html(G: nx.Graph, output: Path) -> None:
    """Render G as an interactive vis.js HTML file."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    communities = detect_communities(G)
    nx.set_node_attributes(G, communities, "community")

    vis_nodes = []
    for node_id, attrs in G.nodes(data=True):
        community = attrs.get("community", 0)
        color = _PALETTE[community % len(_PALETTE)]
        degree = G.degree(node_id)
        vis_nodes.append({
            "id": node_id,
            "label": attrs.get("title", node_id)[:40],
            "title": attrs.get("title", node_id),
            "value": degree,
            "color": color,
            "url": attrs.get("url", ""),
        })

    vis_edges = []
    for i, (src, dst, attrs) in enumerate(G.edges(data=True)):
        edge_type = attrs.get("type", "INFERRED")
        opacity = min(1.0, max(0.2, attrs.get("weight", 0.5)))
        vis_edges.append({
            "id": i,
            "from": src,
            "to": dst,
            "color": {"color": _EDGE_COLORS.get(edge_type, "#888"), "opacity": opacity},
            "title": attrs.get("label", edge_type),
        })

    n_communities = len(set(communities.values())) if communities else 0
    html = _HTML_TEMPLATE.format(
        vis_cdn=_VIS_CDN,
        node_count=len(vis_nodes),
        edge_count=len(vis_edges),
        community_count=n_communities,
        nodes_json=json.dumps(vis_nodes),
        edges_json=json.dumps(vis_edges),
    )
    Path(output).write_text(html, encoding="utf-8")


def export_json(G: nx.Graph, output: Path) -> None:
    """Write graph as JSON {nodes: [...], edges: [...]} for programmatic querying."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [
            {"id": n, **{k: v for k, v in attrs.items()}}
            for n, attrs in G.nodes(data=True)
        ],
        "edges": [
            {"from": src, "to": dst, **attrs}
            for src, dst, attrs in G.edges(data=True)
        ],
    }
    Path(output).write_text(json.dumps(data, indent=2), encoding="utf-8")
