"""
diagnose_cooccurrence_thresholds.py

Purpose
-------
Given a "no metadata" incidence matrix (rows = cases; columns = tropes/features)
with 'X' marking presence and blank marking absence, this script:

1) converts the matrix to binary (X->1, else 0)
2) computes the trope–trope co-occurrence matrix via projection
3) prints, for a set of EDGE-WEIGHT thresholds, the resulting:
   - number of surviving nodes (tropes with >=1 qualifying edge)
   - number of qualifying edges (unique trope pairs)
   - total possible pairs among surviving nodes
   - density (edges / possible pairs)

Use case
--------
Pick an edge threshold that yields a Gephi network that is computationally
manageable and visually interpretable.

Inputs
------
- Excel: "full database (no metadata).xlsx" (edit filename as needed)
  OR
- CSV:   "full database (no metadata).csv"

Output
------
Printed table to the console.
"""

import pandas as pd
import numpy as np

# 1) Load your full “no metadata” sheet (rows = cases; cols = tropes/features)
df = pd.read_excel("full database (no metadata).xlsx", index_col=None)
# If you have a CSV instead, use:
# df = pd.read_csv("full database (no metadata).csv")

# 2) Binarize X → 1, blank → 0
incidence = (df == "X").astype(int)

# 3) Compute the co-occurrence matrix (tropes x tropes)
cooc = incidence.T.dot(incidence)

# 4) Build a strict upper-triangle mask (exclude diagonal/self-pairs)
n = cooc.shape[0]
upper_mask = np.triu(np.ones((n, n), dtype=bool), k=1)

# 5) Extract raw values once
vals = cooc.values

print("Thr  Nodes  Edges      PossiblePairs   Density")
for thr in [1, 2, 3, 5, 10, 15, 20]:
    # Edges at/above threshold (upper triangle only, to avoid double-counting)
    edges_upper = (vals >= thr) & upper_mask
    E = int(edges_upper.sum())

    # Nodes that participate in at least one qualifying edge
    # (symmetrize the upper-triangle boolean matrix)
    edges_sym = edges_upper | edges_upper.T
    N = int(edges_sym.any(axis=1).sum())

    # Total possible pairs among the surviving nodes
    possible_pairs = N * (N - 1) // 2

    # Density among surviving nodes (guard against divide-by-zero)
    density = (E / possible_pairs) if possible_pairs else 0.0

    print(f"≥{thr:>2d}  {N:>5,}  {E:>9,}  {possible_pairs:>13,}  {density:>7.4f}")