#!/usr/bin/env python3
"""
k_components_from_gexf.py

Compute k-components (k-vertex-connected components) on an existing network file
(e.g., a trope–trope co-occurrence network already exported as GEXF), and export:

1) A summary CSV listing all k-components
2) One GEXF subgraph per k-component (for Gephi)
3) One CSV node list per k-component
4) A node-level CSV of k-core numbers (core_number) for quick structural ranking

Why this script exists:
- Network construction (incidence → co-occurrence GEXF) belongs in 02_networks.
- This script is purely topology analysis on an already-built graph.

Requires: pandas, networkx
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import networkx as nx

# NetworkX import paths can vary; try robustly.
try:
    from networkx.algorithms.connectivity import k_components  # NetworkX 3.x
except Exception:  # pragma: no cover
    try:
        from networkx.algorithms.connectivity.kcomponents import k_components
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "Could not import k_components from NetworkX. "
            "Please install/upgrade NetworkX (>= 2.8 recommended; 3.x ideal)."
        ) from e


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG (edit per dataset / network)
# ──────────────────────────────────────────────────────────────────────────────

# Input network file (GEXF). Default can point to your 7-book demo output.
INPUT_GEXF = Path("trope_cooccurrence_thr2.gexf")

# Output directory
OUTDIR = Path("k_components_output")

# Optionally export only certain k-levels (e.g., [2,3,4]).
# None = export all k-levels returned by k_components().
EXPORT_ONLY_K: Optional[List[int]] = None

# If True, write a node-level CSV with k-core numbers (core_number).
EXPORT_CORE_NUMBERS = True
CORE_NUMBERS_CSV = "node_core_numbers.csv"

# If True, also write a node-level CSV with degree and weighted degree (if weights exist).
EXPORT_NODE_SUMMARY = True
NODE_SUMMARY_CSV = "node_summary.csv"

# Edge weight attribute name (common: "weight"). Used only for weighted degree.
WEIGHT_ATTR = "weight"

# Filename prefix for per-component outputs
COMPONENT_PREFIX = "kcomp"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_undirected(G: nx.Graph) -> nx.Graph:
    """
    k_components is defined for undirected graphs. If a directed graph is read,
    convert it to undirected (preserving weights by summing parallel directions if present).
    """
    if not G.is_directed():
        return G

    # Convert to undirected; if reciprocal edges exist, NetworkX keeps one edge.
    # We'll preserve weights by summing u->v and v->u weights when both exist.
    H = nx.Graph()
    H.add_nodes_from(G.nodes(data=True))

    for u, v, data in G.edges(data=True):
        w = data.get(WEIGHT_ATTR, 1)
        if H.has_edge(u, v):
            H[u][v][WEIGHT_ATTR] = H[u][v].get(WEIGHT_ATTR, 1) + w
        else:
            H.add_edge(u, v, **data)

    return H


def _infer_has_weights(G: nx.Graph, weight_attr: str) -> bool:
    for _, _, d in G.edges(data=True):
        if weight_attr in d:
            return True
    return False


def _write_node_summaries(G: nx.Graph, outdir: Path) -> None:
    """Export core numbers (k-core) and basic node summary stats."""
    outdir.mkdir(parents=True, exist_ok=True)

    # k-core numbers (node embeddedness)
    if EXPORT_CORE_NUMBERS:
        core = nx.core_number(G)
        pd.DataFrame(
            {"node": list(core.keys()), "core_number": list(core.values())}
        ).sort_values(["core_number", "node"], ascending=[False, True]).to_csv(
            outdir / CORE_NUMBERS_CSV, index=False, encoding="utf-8"
        )

    # Degree summaries
    if EXPORT_NODE_SUMMARY:
        has_w = _infer_has_weights(G, WEIGHT_ATTR)
        deg = dict(G.degree())
        if has_w:
            wdeg = dict(G.degree(weight=WEIGHT_ATTR))
        else:
            wdeg = {n: float("nan") for n in G.nodes()}

        pd.DataFrame(
            {
                "node": list(G.nodes()),
                "degree": [deg[n] for n in G.nodes()],
                "weighted_degree": [wdeg[n] for n in G.nodes()],
            }
        ).sort_values(["degree", "node"], ascending=[False, True]).to_csv(
            outdir / NODE_SUMMARY_CSV, index=False, encoding="utf-8"
        )


def _write_k_components(
    G: nx.Graph,
    kcomp: Dict[int, List[set]],
    outdir: Path,
    export_only_k: Optional[List[int]] = None,
) -> Path:
    """Export each k-component as GEXF + node list CSV, and write a summary CSV."""
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    ks = sorted(kcomp.keys())
    if export_only_k is not None:
        ks = [k for k in ks if k in set(export_only_k)]

    for k in ks:
        comps = kcomp[k]
        for i, node_set in enumerate(comps, start=1):
            sub = G.subgraph(node_set).copy()

            gexf_name = f"{COMPONENT_PREFIX}_k{k}_component_{i}.gexf"
            csv_name = f"{COMPONENT_PREFIX}_k{k}_component_{i}_nodes.csv"

            nx.write_gexf(sub, outdir / gexf_name)

            pd.DataFrame({"node": sorted(node_set)}).to_csv(
                outdir / csv_name, index=False, encoding="utf-8"
            )

            rows.append(
                {
                    "k": k,
                    "component_id": i,
                    "num_nodes": sub.number_of_nodes(),
                    "num_edges": sub.number_of_edges(),
                    "gexf_file": gexf_name,
                    "nodes_csv": csv_name,
                }
            )

    summary = pd.DataFrame(rows).sort_values(["k", "component_id"])
    summary_path = outdir / f"{COMPONENT_PREFIX}_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8")
    return summary_path


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not INPUT_GEXF.exists():
        raise FileNotFoundError(f"Input GEXF not found: {INPUT_GEXF}")

    G = nx.read_gexf(INPUT_GEXF)

    # Ensure undirected for k-components
    G = _ensure_undirected(G)

    if G.number_of_nodes() == 0:
        print("Graph has 0 nodes. Nothing to analyze.")
        return

    if G.number_of_edges() == 0:
        print("Graph has 0 edges. k-components are not meaningful on an edgeless graph.")
        return

    OUTDIR.mkdir(parents=True, exist_ok=True)

    # Export node-level summaries (core numbers, etc.)
    _write_node_summaries(G, OUTDIR)

    # Compute k-components
    kcomp = k_components(G)  # dict: {k: [set(nodes), ...], ...}

    # Export per-component subgraphs + summary
    summary_path = _write_k_components(G, kcomp, OUTDIR, export_only_k=EXPORT_ONLY_K)

    # Console summary
    ks = sorted(kcomp.keys())
    if EXPORT_ONLY_K is not None:
        ks = [k for k in ks if k in set(EXPORT_ONLY_K)]

    print("[✓] k-components computed.")
    print(f"    Input:    {INPUT_GEXF}")
    print(f"    Graph:    {G.number_of_nodes():,} nodes | {G.number_of_edges():,} edges")
    print(f"    k-levels: {ks}")
    print(f"    Outputs:  {OUTDIR.resolve()}")
    print(f"    Summary:  {summary_path.resolve()}")
    if EXPORT_CORE_NUMBERS:
        print(f"    Core #:   {(OUTDIR / CORE_NUMBERS_CSV).resolve()}")
    if EXPORT_NODE_SUMMARY:
        print(f"    Node sum: {(OUTDIR / NODE_SUMMARY_CSV).resolve()}")


if __name__ == "__main__":
    main()