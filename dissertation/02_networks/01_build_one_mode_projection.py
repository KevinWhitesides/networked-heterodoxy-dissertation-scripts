#!/usr/bin/env python3
"""
01_build_one_mode_projection.py

One-Mode Co-Occurrence Network Builder
(Binary Incidence → Weighted Projection → Thresholded Networks)

Given a binary incidence matrix (rows = cases; columns = items/tropes),
this script:

1) Optionally drops specified columns (metadata safeguard)
2) Applies a global minimum node frequency threshold (default = 2)
3) Computes a weighted one-mode projection
4) Generates separate graphs for each specified edge threshold
5) Exports:
   - Edge list CSV
   - GEXF network (with node attributes)

Assumptions:
- Presence marked with "X"
- Absence blank
- No totals rows
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import networkx as nx
from pathlib import Path


# =========================
# USER SETTINGS
# =========================

INPUT_PATH = "full database (no metadata).xlsx"  # .xlsx or .csv
PRESENCE_TOKEN = "X"

DROP_COLUMNS = []  # Optional safeguard, e.g. ["Title"]

MIN_NODE_FREQ = 2  # Minimum number of cases an item must appear in

EDGE_THRESHOLDS = [20, 30, 40]  # Edge weight thresholds


# =========================
# LOAD DATA
# =========================

def load_table(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p.resolve()}")

    if p.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(p, index_col=None)
    elif p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    else:
        raise ValueError("Unsupported file type. Use .xlsx or .csv.")


df = load_table(INPUT_PATH)

# Drop optional metadata columns
if DROP_COLUMNS:
    df = df.drop(columns=DROP_COLUMNS)

# =========================
# BINARIZE
# =========================

incidence = (df == PRESENCE_TOKEN).astype(np.int8)

# Compute raw frequency (column sums)
freq = incidence.sum(axis=0)

# Apply global node frequency filter
if MIN_NODE_FREQ > 1:
    keep_cols = freq[freq >= MIN_NODE_FREQ].index
    incidence = incidence[keep_cols]
    freq = freq[keep_cols]

print(f"\nApplied MIN_NODE_FREQ = {MIN_NODE_FREQ}")
print(f"Retained {len(freq):,} nodes after frequency filtering")

# =========================
# PROJECTION
# =========================

cooc = incidence.T.dot(incidence)

n_total = cooc.shape[0]
upper_mask = np.triu(np.ones((n_total, n_total), dtype=bool), k=1)

dataset_stem = Path(INPUT_PATH).stem


# =========================
# THRESHOLD LOOP
# =========================

for thr in EDGE_THRESHOLDS:

    rows, cols = np.where((cooc.values >= thr) & upper_mask)
    weights = cooc.values[rows, cols]

    edges_df = pd.DataFrame({
        "source": cooc.index[rows],
        "target": cooc.columns[cols],
        "weight": weights
    })

    # Build graph
    G = nx.from_pandas_edgelist(
        edges_df,
        source="source",
        target="target",
        edge_attr="weight"
    )

    # Add node attributes
    for node in G.nodes():
        G.nodes[node]["frequency"] = int(freq[node])

    # Add structural metrics
    degree_dict = dict(G.degree())
    weighted_degree_dict = dict(G.degree(weight="weight"))

    nx.set_node_attributes(G, degree_dict, "degree")
    nx.set_node_attributes(G, weighted_degree_dict, "weighted_degree")

    # Compute density among surviving nodes
    N = G.number_of_nodes()
    E = G.number_of_edges()
    possible_pairs = N * (N - 1) // 2
    density = E / possible_pairs if possible_pairs else 0

    # Export files
    edges_fname = f"{dataset_stem}_thr{thr}_edges.csv"
    gexf_fname = f"{dataset_stem}_thr{thr}.gexf"

    edges_df.to_csv(edges_fname, index=False)
    nx.write_gexf(G, gexf_fname)

    print(f"\nThreshold ≥ {thr}")
    print(f"  Nodes: {N:,}")
    print(f"  Edges: {E:,}")
    print(f"  Density: {density:.4f}")
    print(f"  → Wrote {edges_fname}")
    print(f"  → Wrote {gexf_fname}")

print("\nDone.\n")