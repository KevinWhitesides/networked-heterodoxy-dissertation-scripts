#!/usr/bin/env python3
"""
cluster_from_similarity_matrix.py

Given a square similarity matrix (case × case), this script:

1) Converts similarity to distance: distance = 1 - similarity
2) Performs hierarchical clustering on the distance matrix
3) Assigns each case to a cluster using either:
   - a fixed number of clusters (N_CLUSTERS), or
   - a distance cutoff (DISTANCE_CUTOFF)
4) Writes:
   - cluster assignments CSV
   - cluster summary stats CSV (avg intra-cluster similarity)
   - per-case mean similarity to others in its cluster CSV
   - optional dendrogram PNG

Designed for Jaccard similarity outputs from incidence matrices,
but works for any valid similarity matrix in [0, 1].
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG (edit per dataset)
# ──────────────────────────────────────────────────────────────────────────────

# Input similarity matrix CSV (square; same labels on rows/cols)
INPUT_SIM_CSV = Path("7book_jaccard_threshold2.csv")

# Similarity → distance transform
# For Jaccard similarity: distance = 1 - similarity
DISTANCE_MODE = "one_minus"  # currently only supported mode

# Linkage method.
# For precomputed (non-Euclidean) distances like 1-Jaccard, "average" or "complete"
# are easier to defend than "ward".
LINKAGE_METHOD = "average"   # options: "average", "complete", "single", "ward" (not recommended here)

# Choose exactly one clustering rule:
N_CLUSTERS: Optional[int] = 3         # fixed-k clusters (default for demo)
DISTANCE_CUTOFF: Optional[float] = None  # e.g., 0.65 to let k emerge

# Output directory + filenames
OUTPUT_DIR = Path(".")
OUT_ASSIGNMENTS = "clusters.csv"
OUT_CLUSTER_SUMMARY = "cluster_summary.csv"
OUT_CASE_TO_CLUSTER = "case_similarity_to_cluster.csv"

# Optional dendrogram plot
WRITE_DENDROGRAM = True
OUT_DENDROGRAM_PNG = "dendrogram.png"
DENDROGRAM_FIGSIZE = (10, 6)
DPI = 300


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _validate_square_matrix(df: pd.DataFrame) -> None:
    if df.shape[0] != df.shape[1]:
        raise ValueError(f"Matrix must be square. Got shape {df.shape}.")

    if list(df.index) != list(df.columns):
        # Not always fatal, but strongly suggests misalignment
        raise ValueError(
            "Row labels and column labels do not match. "
            "Similarity matrix should have identical row/column labels in the same order."
        )

    vals = df.to_numpy(dtype=float)
    if np.any(vals < 0) or np.any(vals > 1):
        raise ValueError("Similarity values should be in [0, 1].")

    # Diagonal should be 1.0 (self similarity). Allow small float noise.
    diag = np.diag(vals)
    if not np.allclose(diag, 1.0, atol=1e-6):
        raise ValueError("Diagonal should be 1.0 for a similarity matrix.")


def _similarity_to_distance(sim: np.ndarray) -> np.ndarray:
    if DISTANCE_MODE == "one_minus":
        dist = 1.0 - sim
    else:
        raise ValueError(f"Unsupported DISTANCE_MODE: {DISTANCE_MODE}")

    # Enforce exact zero diagonal for squareform
    np.fill_diagonal(dist, 0.0)
    return dist


def _avg_intra_cluster_similarity(sim_df: pd.DataFrame, members: List[str]) -> float:
    sub = sim_df.loc[members, members].to_numpy(dtype=float)
    if sub.shape[0] <= 1:
        return float("nan")  # no pairwise comparisons possible

    mask = ~np.eye(sub.shape[0], dtype=bool)
    return float(sub[mask].mean())


def _case_mean_similarity_to_cluster(sim_df: pd.DataFrame, case: str, members: List[str]) -> float:
    others = [m for m in members if m != case]
    if not others:
        return float("nan")
    return float(sim_df.loc[case, others].mean())


def _write_dendrogram(linkage_matrix: np.ndarray, labels: List[str], out_png: Path) -> None:
    import matplotlib.pyplot as plt
    from scipy.cluster.hierarchy import dendrogram

    fig, ax = plt.subplots(figsize=DENDROGRAM_FIGSIZE, constrained_layout=True)
    dendrogram(linkage_matrix, labels=labels, leaf_rotation=45, ax=ax)
    ax.set_title(f"Hierarchical Clustering Dendrogram ({LINKAGE_METHOD})")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if N_CLUSTERS is not None and DISTANCE_CUTOFF is not None:
        raise ValueError("Set only one of N_CLUSTERS or DISTANCE_CUTOFF (not both).")

    sim_df = pd.read_csv(INPUT_SIM_CSV, index_col=0)
    sim_df.index = sim_df.index.map(str)
    sim_df.columns = sim_df.columns.map(str)

    _validate_square_matrix(sim_df)

    labels = list(sim_df.index)
    sim = sim_df.to_numpy(dtype=float)

    dist_sq = _similarity_to_distance(sim)
    condensed = squareform(dist_sq, checks=True)

    link = linkage(condensed, method=LINKAGE_METHOD)

    # Cluster assignment
    if DISTANCE_CUTOFF is not None:
        clusters = fcluster(link, t=DISTANCE_CUTOFF, criterion="distance")
        rule_desc = f"distance cutoff ≤ {DISTANCE_CUTOFF}"
    else:
        # Default demo behavior: fixed k
        k = int(N_CLUSTERS) if N_CLUSTERS is not None else 3
        clusters = fcluster(link, t=k, criterion="maxclust")
        rule_desc = f"maxclust = {k}"

    cluster_df = pd.DataFrame({"Case": labels, "Cluster": clusters})
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    out_assign = OUTPUT_DIR / OUT_ASSIGNMENTS
    out_summary = OUTPUT_DIR / OUT_CLUSTER_SUMMARY
    out_casefit = OUTPUT_DIR / OUT_CASE_TO_CLUSTER
    out_dendro = OUTPUT_DIR / OUT_DENDROGRAM_PNG

    cluster_df.to_csv(out_assign, index=False, encoding="utf-8")

    # Cluster summaries
    cluster_summaries: List[Dict[str, object]] = []
    case_fit_rows: List[Dict[str, object]] = []

    for cid in sorted(cluster_df["Cluster"].unique()):
        members = cluster_df.loc[cluster_df["Cluster"] == cid, "Case"].tolist()
        avg_sim = _avg_intra_cluster_similarity(sim_df, members)
        cluster_summaries.append({
            "Cluster": cid,
            "n_cases": len(members),
            "avg_intra_similarity": avg_sim,
        })

        for case in members:
            mean_to_cluster = _case_mean_similarity_to_cluster(sim_df, case, members)
            case_fit_rows.append({
                "Case": case,
                "Cluster": cid,
                "avg_similarity_to_cluster": mean_to_cluster,
            })

    pd.DataFrame(cluster_summaries).to_csv(out_summary, index=False, encoding="utf-8")
    pd.DataFrame(case_fit_rows).to_csv(out_casefit, index=False, encoding="utf-8")

    if WRITE_DENDROGRAM:
        _write_dendrogram(link, labels, out_dendro)

    # Console summary
    print("Clustering complete.")
    print(f"  Input similarity CSV:   {INPUT_SIM_CSV}")
    print(f"  Linkage method:         {LINKAGE_METHOD}")
    print(f"  Cluster rule:           {rule_desc}")
    print(f"  Wrote assignments:      {out_assign}")
    print(f"  Wrote cluster summary:  {out_summary}")
    print(f"  Wrote case-fit table:   {out_casefit}")
    if WRITE_DENDROGRAM:
        print(f"  Wrote dendrogram PNG:   {out_dendro}")


if __name__ == "__main__":
    main()