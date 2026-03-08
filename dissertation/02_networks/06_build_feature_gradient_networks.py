#!/usr/bin/env python3
"""
05_build_feature_gradient_networks.py

Build network and diagnostic outputs for a selected feature gradient found by
03_similarity/07_find_feature_gradients.py.

This script takes one selected feature gradient chain (for example
Feature A -> Feature B -> Feature C -> Feature D -> Feature E) and builds:

1) feature_gradient_bipartite.gexf
   A feature × case bipartite network for the selected gradient

2) feature_gradient_jaccard_subset.csv
   The feature × feature Jaccard matrix for the selected gradient features

3) feature_gradient_jaccard_pairs_ranked.csv
   Ranked pairwise similarity table for the selected gradient features

4) feature_gradient_jaccard_heatmap.png
   A heatmap of the selected feature-gradient Jaccard structure

5) analysis_summary.txt
   A compact record of the selected gradient, thresholds, and output statistics

Typical workflow
----------------
1) Run 03_similarity/07_find_feature_gradients.py to produce:
      feature_gradients.csv
2) Select one feature gradient from that table
3) Run this script to build graph / heatmap outputs for it
"""

from __future__ import annotations

from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import List, Sequence

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

# Inputs
GRADIENTS_CSV = Path("feature_gradients.csv")
INCIDENCE_PATH = Path("input_incidence_matrix.xlsx")   # .xlsx or .csv
SHEET_NAME = 0

# Incidence matrix structure
CASE_ID_COLUMN = "Source Title"
N_METADATA_COLS = 4
PRESENCE_TOKEN = "X"

# Gradient selection mode
#   "row"      -> use SELECTED_ROW (0-based row index in feature_gradients.csv)
#   "endpoint" -> use FEATURE_A and FEATURE_E, then choose the top-ranked row for that pair
#   "chain"    -> use EXACT_CHAIN_STRING exactly as stored in the "chain" column
SELECTION_MODE = "row"          # "row", "endpoint", or "chain"
SELECTED_ROW = 0

FEATURE_A = ""
FEATURE_E = ""

EXACT_CHAIN_STRING = ""

# Case-retention threshold within the selected gradient support graph
# Default = 2, so a case must contain at least two selected gradient features
MIN_GRADIENT_FEATURES_PER_CASE = 2

# Optional label shortening for long case titles
SHORTEN_CASE_LABELS = True
TITLE_MAX_LEN = 36
APPEND_ID_FOR_UNIQUENESS = True

# Output
OUTPUT_DIR = Path(".")
OUT_BIP_GEXF = "feature_gradient_bipartite.gexf"
OUT_JACCARD_CSV = "feature_gradient_jaccard_subset.csv"
OUT_JACCARD_PAIRS = "feature_gradient_jaccard_pairs_ranked.csv"
OUT_JACCARD_PNG = "feature_gradient_jaccard_heatmap.png"
OUT_SUMMARY = "analysis_summary.txt"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def read_table(path: Path, sheet_name=0) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=str, keep_default_na=False)
    elif suffix == ".csv":
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="latin-1")
    else:
        raise ValueError(f"Unsupported input format: {suffix}. Use .xlsx/.xls or .csv.")

    df.columns = df.columns.map(str)
    return df


def get_feature_columns(df: pd.DataFrame, n_metadata_cols: int) -> List[str]:
    if n_metadata_cols < 0 or n_metadata_cols >= df.shape[1]:
        raise ValueError(
            f"N_METADATA_COLS={n_metadata_cols} invalid for table with {df.shape[1]} columns."
        )
    return list(df.columns[n_metadata_cols:])


def binarize_presence(df: pd.DataFrame, feature_cols: Sequence[str], token: str) -> pd.DataFrame:
    truthy = {"x", "✓", "check", "true", "1", "y", "yes"}

    def to_bin(col: pd.Series) -> pd.Series:
        if pd.api.types.is_numeric_dtype(col):
            return (col.fillna(0).astype(float) > 0).astype(np.uint8)

        s = col.fillna("").astype(str).str.strip().str.lower()
        return s.apply(
            lambda v: 1
            if v == token.lower() or v in truthy or (v.isdigit() and int(v) > 0)
            else 0
        ).astype(np.uint8)

    return df[feature_cols].apply(to_bin)


def make_short_titles(titles: List[str], max_len: int, append_id: bool) -> dict[str, str]:
    mapping: dict[str, str] = {}
    seen = set()

    for idx, full in enumerate(titles, start=1):
        t = " ".join(str(full).split()).strip()

        if ":" in t:
            t = t.split(":", 1)[0].strip()

        if len(t) <= max_len:
            cand = t
        else:
            cut = t[:max_len]
            if " " in cut:
                cut = cut[:cut.rfind(" ")]
            cand = cut + "…"

        if append_id:
            cand = f"{cand} [{idx}]"

        base = cand
        k = 2
        while cand in seen:
            suffix = f"({k})"
            trunc = max(0, max_len - len(suffix) - 1)
            trunk = base if len(base) <= trunc else base[:trunc] + "…"
            cand = f"{trunk} {suffix}"
            k += 1

        mapping[full] = cand
        seen.add(cand)

    return mapping


def select_gradient_row(df: pd.DataFrame) -> pd.Series:
    if "chain" not in df.columns:
        raise ValueError("GRADIENTS_CSV must contain a 'chain' column.")

    if SELECTION_MODE == "row":
        if SELECTED_ROW < 0 or SELECTED_ROW >= len(df):
            raise ValueError(f"SELECTED_ROW {SELECTED_ROW} is out of range for {len(df)} rows.")
        return df.iloc[SELECTED_ROW]

    if SELECTION_MODE == "endpoint":
        if not FEATURE_A or not FEATURE_E:
            raise ValueError("For SELECTION_MODE='endpoint', set FEATURE_A and FEATURE_E.")

        sub = df[
            ((df["feature_A"].astype(str) == str(FEATURE_A)) & (df["feature_E"].astype(str) == str(FEATURE_E))) |
            ((df["feature_A"].astype(str) == str(FEATURE_E)) & (df["feature_E"].astype(str) == str(FEATURE_A)))
        ].copy()

        if sub.empty:
            raise ValueError(f"No feature gradient rows found for endpoint pair ({FEATURE_A}, {FEATURE_E}).")

        return sub.iloc[0]

    if SELECTION_MODE == "chain":
        if not EXACT_CHAIN_STRING:
            raise ValueError("For SELECTION_MODE='chain', set EXACT_CHAIN_STRING.")

        sub = df[df["chain"].astype(str) == str(EXACT_CHAIN_STRING)].copy()
        if sub.empty:
            raise ValueError(f"No feature gradient row found with chain string:\n{EXACT_CHAIN_STRING}")
        return sub.iloc[0]

    raise ValueError("SELECTION_MODE must be 'row', 'endpoint', or 'chain'.")


def parse_chain(chain_string: str) -> List[str]:
    parts = [p.strip() for p in str(chain_string).split("|")]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse a valid chain from: {chain_string}")
    return parts


def build_feature_bipartite(
    subset_df: pd.DataFrame,
    case_id_col: str,
    gradient_features: List[str],
    short_case_labels: bool = True,
    title_max_len: int = 36,
    append_id: bool = True,
) -> tuple[nx.Graph, list[str], list[str]]:
    """
    Build a feature × case bipartite network from the selected gradient features
    and retained supporting cases.
    """
    retained_titles = subset_df[case_id_col].astype(str).tolist()

    if short_case_labels:
        short_map = make_short_titles(retained_titles, title_max_len, append_id)
    else:
        short_map = {t: t for t in retained_titles}

    G = nx.Graph()

    # Feature nodes first (focal side)
    for feat in gradient_features:
        G.add_node(
            f"feature::{feat}",
            label=feat,
            type="feature",
            bipartite=0,
        )

    # Case nodes
    for full in retained_titles:
        G.add_node(
            f"case::{full}",
            label=short_map.get(full, full),
            full_title=full,
            type="case",
            bipartite=1,
        )

    # Edges
    for _, row in subset_df.iterrows():
        case = str(row[case_id_col])
        for feat in gradient_features:
            if int(row[feat]) == 1:
                G.add_edge(f"feature::{feat}", f"case::{case}", weight=1)

    return G, retained_titles, gradient_features


def compute_feature_jaccard_subset(subset_df: pd.DataFrame, gradient_features: List[str]) -> pd.DataFrame:
    """
    Compute feature × feature Jaccard matrix for the selected gradient features.
    """
    X = subset_df[gradient_features].to_numpy(dtype=np.uint8)
    n = len(gradient_features)
    mat = np.zeros((n, n), dtype=float)

    # columns are features
    for i in range(n):
        ai = X[:, i]
        for j in range(i, n):
            bj = X[:, j]
            inter = int(np.bitwise_and(ai, bj).sum())
            union = int(np.bitwise_or(ai, bj).sum())
            jacc = (inter / union) if union > 0 else 0.0
            mat[i, j] = jacc
            mat[j, i] = jacc

    return pd.DataFrame(mat, index=gradient_features, columns=gradient_features)


def build_ranked_feature_pairs(subset_df: pd.DataFrame, gradient_features: List[str]) -> pd.DataFrame:
    """
    Ranked pair table for the selected gradient features.
    """
    X = subset_df[gradient_features].to_numpy(dtype=np.uint8)
    rows = []

    for i, j in combinations(range(len(gradient_features)), 2):
        ai = X[:, i]
        bj = X[:, j]
        inter = int(np.bitwise_and(ai, bj).sum())
        union = int(np.bitwise_or(ai, bj).sum())
        jacc = (inter / union) if union > 0 else 0.0

        rows.append({
            "feature_1": gradient_features[i],
            "feature_2": gradient_features[j],
            "shared_cases": inter,
            "union_cases": union,
            "jaccard": round(jacc, 6),
        })

    out = pd.DataFrame(rows)
    return out.sort_values(["jaccard", "shared_cases", "feature_1", "feature_2"], ascending=[False, False, True, True]).reset_index(drop=True)


def write_heatmap(jacc_df: pd.DataFrame, out_png: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    im = ax.imshow(jacc_df.values, aspect="auto", interpolation="nearest")

    ax.set_xticks(np.arange(len(jacc_df.columns)))
    ax.set_yticks(np.arange(len(jacc_df.index)))
    ax.set_xticklabels(jacc_df.columns, rotation=45, ha="right")
    ax.set_yticklabels(jacc_df.index)

    ax.set_title("Feature Jaccard Similarity Within Selected Gradient")
    ax.set_xlabel("Features")
    ax.set_ylabel("Features")

    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Jaccard similarity")

    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Read gradient table and select one feature chain
    if not GRADIENTS_CSV.exists():
        raise FileNotFoundError(f"Feature gradient CSV not found: {GRADIENTS_CSV}")

    grad_df = pd.read_csv(GRADIENTS_CSV)
    grad_df.columns = grad_df.columns.map(str)

    selected_row = select_gradient_row(grad_df)
    selected_chain = parse_chain(str(selected_row["chain"]))

    endpoint_A = str(selected_row["feature_A"]) if "feature_A" in selected_row.index else selected_chain[0]
    endpoint_E = str(selected_row["feature_E"]) if "feature_E" in selected_row.index else selected_chain[-1]

    # 2) Read incidence matrix and binarize
    df_raw = read_table(INCIDENCE_PATH, sheet_name=SHEET_NAME)

    if CASE_ID_COLUMN not in df_raw.columns:
        raise ValueError(f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in incidence matrix.")

    case_index = df_raw.columns.get_loc(CASE_ID_COLUMN)
    if case_index >= N_METADATA_COLS:
        raise ValueError(
            f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' is outside the first {N_METADATA_COLS} columns.\n"
            "This script assumes that all metadata columns appear to the LEFT of the feature columns."
        )

    feature_cols = get_feature_columns(df_raw, N_METADATA_COLS)
    if not feature_cols:
        raise ValueError("No feature columns found. Check N_METADATA_COLS.")

    df = pd.concat([df_raw[[CASE_ID_COLUMN]], df_raw[feature_cols]], axis=1)
    bin_features = binarize_presence(df, feature_cols, PRESENCE_TOKEN)
    df_bin = pd.concat([df[[CASE_ID_COLUMN]], bin_features], axis=1)
    df_bin[CASE_ID_COLUMN] = df_bin[CASE_ID_COLUMN].astype(str)

    # Validate selected features
    available_features = set(feature_cols)
    missing = [f for f in selected_chain if f not in available_features]
    if missing:
        raise ValueError(f"These features from the selected gradient were not found in the incidence matrix: {missing}")

    # 3) Retain supporting cases
    # Keep cases containing at least MIN_GRADIENT_FEATURES_PER_CASE selected gradient features
    support_counts = df_bin[selected_chain].sum(axis=1)
    subset_df = df_bin.loc[support_counts >= MIN_GRADIENT_FEATURES_PER_CASE, [CASE_ID_COLUMN] + selected_chain].copy()

    if subset_df.empty:
        raise ValueError(
            "No cases remain after applying MIN_GRADIENT_FEATURES_PER_CASE. "
            "Try lowering the threshold."
        )

    # 4) Build feature × case bipartite graph
    G_bip, retained_titles, retained_features = build_feature_bipartite(
        subset_df=subset_df,
        case_id_col=CASE_ID_COLUMN,
        gradient_features=selected_chain,
        short_case_labels=SHORTEN_CASE_LABELS,
        title_max_len=TITLE_MAX_LEN,
        append_id=APPEND_ID_FOR_UNIQUENESS,
    )

    out_bip_path = OUTPUT_DIR / OUT_BIP_GEXF
    nx.write_gexf(G_bip, out_bip_path)

    # 5) Feature-feature Jaccard subset + ranked pairs + heatmap
    jacc_subset_df = compute_feature_jaccard_subset(subset_df, selected_chain)

    out_jacc_csv = OUTPUT_DIR / OUT_JACCARD_CSV
    jacc_subset_df.to_csv(out_jacc_csv, encoding="utf-8")

    ranked_pairs_df = build_ranked_feature_pairs(subset_df, selected_chain)
    out_pairs_csv = OUTPUT_DIR / OUT_JACCARD_PAIRS
    ranked_pairs_df.to_csv(out_pairs_csv, index=False, encoding="utf-8")

    out_jacc_png = OUTPUT_DIR / OUT_JACCARD_PNG
    write_heatmap(jacc_subset_df, out_jacc_png)

    # 6) Summary
    out_summary = OUTPUT_DIR / OUT_SUMMARY
    with open(out_summary, "w", encoding="utf-8") as f:
        f.write("=== Feature Gradient Network Construction Summary ===\n\n")
        f.write(f"Run timestamp: {run_timestamp}\n\n")

        f.write("Inputs\n")
        f.write("------\n")
        f.write(f"Feature gradient table: {GRADIENTS_CSV}\n")
        f.write(f"Incidence matrix: {INCIDENCE_PATH}\n\n")

        f.write("Gradient selection\n")
        f.write("------------------\n")
        f.write(f"SELECTION_MODE: {SELECTION_MODE}\n")
        if SELECTION_MODE == "row":
            f.write(f"SELECTED_ROW: {SELECTED_ROW}\n")
        elif SELECTION_MODE == "endpoint":
            f.write(f"FEATURE_A: {FEATURE_A}\n")
            f.write(f"FEATURE_E: {FEATURE_E}\n")
        else:
            f.write(f"EXACT_CHAIN_STRING: {EXACT_CHAIN_STRING}\n")
        f.write(f"Selected chain: {' -> '.join(selected_chain)}\n")
        f.write(f"Chain length: {len(selected_chain)}\n")
        f.write(f"Endpoint A: {endpoint_A}\n")
        f.write(f"Endpoint E: {endpoint_E}\n\n")

        f.write("Support-graph settings\n")
        f.write("----------------------\n")
        f.write(f"MIN_GRADIENT_FEATURES_PER_CASE: {MIN_GRADIENT_FEATURES_PER_CASE}\n")
        f.write(f"SHORTEN_CASE_LABELS: {SHORTEN_CASE_LABELS}\n")
        f.write(f"TITLE_MAX_LEN: {TITLE_MAX_LEN}\n")
        f.write(f"APPEND_ID_FOR_UNIQUENESS: {APPEND_ID_FOR_UNIQUENESS}\n\n")

        f.write("Feature × case bipartite network\n")
        f.write("-------------------------------\n")
        f.write(f"Gradient features retained: {len(retained_features)}\n")
        f.write(f"Supporting cases retained: {len(retained_titles)}\n")
        f.write(f"Edges (feature–case links): {G_bip.number_of_edges()}\n\n")

        f.write("Feature Jaccard subset\n")
        f.write("----------------------\n")
        f.write(f"Matrix size: {jacc_subset_df.shape[0]} × {jacc_subset_df.shape[1]}\n")
        if len(jacc_subset_df) > 1:
            mask = ~np.eye(len(jacc_subset_df), dtype=bool)
            offdiag_vals = jacc_subset_df.to_numpy()[mask]
            f.write(f"Minimum off-diagonal Jaccard: {offdiag_vals.min():.6f}\n")
            f.write(f"Maximum off-diagonal Jaccard: {offdiag_vals.max():.6f}\n\n")
        else:
            f.write("Only one feature retained; no off-diagonal similarities.\n\n")

        f.write("Interpretation\n")
        f.write("--------------\n")
        f.write("The bipartite graph shows the selected feature gradient together with the\n")
        f.write("cases that instantiate it. By default, only cases containing at least two\n")
        f.write("selected gradient features are retained, making the support structure of the\n")
        f.write("feature gradient easier to interpret. The Jaccard outputs provide a compact\n")
        f.write("feature-similarity view of the same selected gradient.\n\n")

        f.write("Output files\n")
        f.write("------------\n")
        f.write(f"{OUT_BIP_GEXF}\n")
        f.write(f"{OUT_JACCARD_CSV}\n")
        f.write(f"{OUT_JACCARD_PAIRS}\n")
        f.write(f"{OUT_JACCARD_PNG}\n")
        f.write(f"{OUT_SUMMARY}\n")

    print("[✓] Feature gradient network construction complete.")
    print(f"    Selected chain:      {' -> '.join(selected_chain)}")
    print(f"    Bipartite GEXF:      {out_bip_path}")
    print(f"    Jaccard CSV:         {out_jacc_csv}")
    print(f"    Ranked pairs CSV:    {out_pairs_csv}")
    print(f"    Jaccard heatmap:     {out_jacc_png}")
    print(f"    Summary:             {out_summary}")


if __name__ == "__main__":
    main()