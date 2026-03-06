#!/usr/bin/env python3
"""
01_diagnose_cooccurrence_thresholds.py

Co-occurrence Threshold Diagnostic (Binary Incidence → One-Mode Projection)

Given a binary incidence matrix (rows = cases; columns = tropes/features) where
presence is marked with "X" and absence is blank, this script:

1) Binarizes the matrix (X -> 1, else 0)
2) Computes the one-mode trope–trope co-occurrence matrix via projection
3) For each EDGE-WEIGHT threshold, reports:
   - Edges: number of qualifying trope pairs (co-occurrence >= threshold)
   - Nodes: number of surviving tropes participating in >=1 qualifying edge
   - PossiblePairs: N*(N-1)/2 among surviving nodes
   - Density: Edges / PossiblePairs (density among surviving nodes)
4) Prints the results and saves them to a CSV file for documentation.

Notes
-----
- Thresholds here are edge-weight thresholds in the projected one-mode network.
- This diagnostic is intended to help select a manageable, interpretable threshold
  prior to exporting a graph to Gephi or computing metrics.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


# =========================
# User settings (edit these)
# =========================

INPUT_PATH = "full database (no metadata).xlsx"  # .xlsx or .csv
PRESENCE_TOKEN = "X"  # what marks "present" in cells
THRESHOLDS = [1, 2, 3, 5, 10, 15, 20]  # edge-weight thresholds to evaluate

# Output: CSV saved next to this script by default
OUTPUT_DIR = Path(__file__).resolve().parent
OUTPUT_BASENAME = "cooccurrence_threshold_diagnostics"  # timestamp will be appended


def load_table(path: str) -> pd.DataFrame:
    """Load an Excel or CSV file into a DataFrame."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p.resolve()}")

    suffix = p.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(p, index_col=None)
    if suffix == ".csv":
        return pd.read_csv(p)

    raise ValueError(f"Unsupported input format '{suffix}'. Use .xlsx/.xls or .csv.")


def main() -> None:
    df = load_table(INPUT_PATH)

    # Binarize presence/absence
    incidence = (df == PRESENCE_TOKEN).astype(np.int8)

    # Co-occurrence projection: tropes x tropes
    cooc = incidence.T.dot(incidence)  # diagonal = trope frequency

    n = cooc.shape[0]
    upper_mask = np.triu(np.ones((n, n), dtype=bool), k=1)
    vals = cooc.values

    rows = []
    for thr in THRESHOLDS:
        edges_upper = (vals >= thr) & upper_mask
        E = int(edges_upper.sum())

        # Symmetrize to compute node survival
        edges_sym = edges_upper | edges_upper.T
        N = int(edges_sym.any(axis=1).sum())

        possible_pairs = N * (N - 1) // 2
        density = (E / possible_pairs) if possible_pairs else 0.0

        rows.append(
            {
                "threshold": thr,
                "nodes_surviving": N,
                "edges_qualifying": E,
                "possible_pairs": int(possible_pairs),
                "density_surviving_nodes": float(density),
            }
        )

    out_df = pd.DataFrame(rows)

    # Print to console
    print("\nCo-occurrence Threshold Diagnostic")
    print(f"Input: {Path(INPUT_PATH).resolve()}")
    print(f"Presence token: {repr(PRESENCE_TOKEN)}\n")

    # Pretty print (human-readable)
    print("Thr  Nodes  Edges      PossiblePairs   Density")
    for r in rows:
        thr = r["threshold"]
        N = r["nodes_surviving"]
        E = r["edges_qualifying"]
        pp = r["possible_pairs"]
        den = r["density_surviving_nodes"]
        print(f"≥{thr:>2d}  {N:>5,}  {E:>9,}  {pp:>13,}  {den:>7.4f}")

    # Save CSV
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_name = f"{OUTPUT_BASENAME}__{ts}.csv"
    out_path = OUTPUT_DIR / out_name
    out_df.to_csv(out_path, index=False)

    print(f"\nSaved CSV: {out_path.resolve()}\n")


if __name__ == "__main__":
    main()