#!/usr/bin/env python3
"""
05_build_feature_absence_network.py

Construct network representations of statistically significant zero-overlap
relationships between features.

This script is designed to work downstream of:

    03_similarity/06_significant_zero_feature_overlap.py

While that script identifies feature pairs that never co-occur in the same case
and evaluates whether those absences are unusual under a degree-preserving null
model, the present script converts those results into network structures
suitable for exploration and visualization.

Outputs
-------
1) feature_absence_graph_sig.gexf
   One-mode feature × feature graph where edges represent statistically
   significant zero-overlap relationships.

2) feature_absence_bipartite.gexf
   Bipartite case × feature graph built from the retained subset of significant
   absence features and the cases that contain them.

3) analysis_summary.txt
   Human-readable record of the run, inputs, thresholds, and graph statistics.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Sequence

import numpy as np
import pandas as pd
import networkx as nx


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

# Inputs
ZERO_FEATURE_OVERLAP_CSV = Path("zero_feature_overlap_with_significance.csv")
INCIDENCE_PATH = Path("input_incidence_matrix.xlsx")   # .xlsx or .csv
SHEET_NAME = 0

# Matrix structure
CASE_ID_COLUMN = "Source Title"
N_METADATA_COLS = 4
PRESENCE_TOKEN = "X"

# Significance selection
SIGNIFICANCE_COLUMN = "sig_0.05"

# Retention filters
MIN_ZERO_NEIGHBORS = 2               # retain features with at least this many significant-zero neighbors
MIN_FEATURES_PER_CASE = 1            # for bipartite graph: case must contain at least this many retained features
MIN_CASES_PER_FEATURE = 2            # for bipartite graph: retained features must appear in at least this many retained cases

# Optional shortening for long case titles in the bipartite graph
SHORTEN_CASE_LABELS = True
TITLE_MAX_LEN = 36
APPEND_ID_FOR_UNIQUENESS = True

# Output
OUTPUT_DIR = Path(".")
OUT_ABS_GRAPH = "feature_absence_graph_sig.gexf"
OUT_BIP_GRAPH = "feature_absence_bipartite.gexf"
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


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Read significant feature zero-overlap table
    if not ZERO_FEATURE_OVERLAP_CSV.exists():
        raise FileNotFoundError(f"Feature zero-overlap CSV not found: {ZERO_FEATURE_OVERLAP_CSV}")

    zero_df = pd.read_csv(ZERO_FEATURE_OVERLAP_CSV)
    zero_df.columns = zero_df.columns.map(str)

    required_cols = {"feature_a", "feature_b", SIGNIFICANCE_COLUMN}
    if not required_cols.issubset(zero_df.columns):
        raise ValueError(
            f"{ZERO_FEATURE_OVERLAP_CSV} must contain columns: {sorted(required_cols)}"
        )

    # Keep only significant pairs
    sig_df = zero_df[zero_df[SIGNIFICANCE_COLUMN].astype(bool)].copy()

    if sig_df.empty:
        raise ValueError(
            f"No feature pairs were significant under {SIGNIFICANCE_COLUMN}."
        )

    # 2) Build one-mode feature absence graph
    G_abs = nx.Graph()

    for _, row in sig_df.iterrows():
        fa = str(row["feature_a"])
        fb = str(row["feature_b"])

        attrs_a = {}
        attrs_b = {}
        if "count_a" in row.index:
            attrs_a["frequency"] = int(row["count_a"])
        if "count_b" in row.index:
            attrs_b["frequency"] = int(row["count_b"])

        if fa not in G_abs:
            G_abs.add_node(fa, label=fa, type="feature", **attrs_a)
        if fb not in G_abs:
            G_abs.add_node(fb, label=fb, type="feature", **attrs_b)

        edge_attrs = {}
        if "p_emp" in row.index:
            edge_attrs["p_emp"] = float(row["p_emp"])
        edge_attrs["significance_column"] = SIGNIFICANCE_COLUMN

        G_abs.add_edge(fa, fb, **edge_attrs)

    # Retain only features with at least MIN_ZERO_NEIGHBORS significant-zero neighbors
    keep_features = {n for n, d in G_abs.degree() if d >= MIN_ZERO_NEIGHBORS}

    if not keep_features:
        raise ValueError(
            f"No features remain after applying MIN_ZERO_NEIGHBORS={MIN_ZERO_NEIGHBORS}."
        )

    G_abs_keep = G_abs.subgraph(keep_features).copy()
    out_abs_path = OUTPUT_DIR / OUT_ABS_GRAPH
    nx.write_gexf(G_abs_keep, out_abs_path)

    # 3) Read incidence matrix and build retained bipartite graph
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

    # Only keep retained significant-absence features that exist in the matrix
    present_keep_features = [f for f in keep_features if f in feature_cols]
    if not present_keep_features:
        raise ValueError("No retained absence features were found in the incidence matrix.")

    df = pd.concat([df_raw[[CASE_ID_COLUMN]], df_raw[present_keep_features]], axis=1).copy()
    bin_features = binarize_presence(df, present_keep_features, PRESENCE_TOKEN)
    df_bin = pd.concat([df[[CASE_ID_COLUMN]].copy(), bin_features], axis=1)
    df_bin[CASE_ID_COLUMN] = df_bin[CASE_ID_COLUMN].astype(str)

    # Case retention: keep cases that contain at least MIN_FEATURES_PER_CASE retained features
    case_feature_counts = df_bin[present_keep_features].sum(axis=1)
    subset_df = df_bin.loc[case_feature_counts >= MIN_FEATURES_PER_CASE].copy()

    if subset_df.empty:
        raise ValueError(
            f"No cases remain after applying MIN_FEATURES_PER_CASE={MIN_FEATURES_PER_CASE}."
        )

    # Refine feature retention inside the retained subset
    subset_feature_counts = subset_df[present_keep_features].sum(axis=0).astype(int)
    bip_features = subset_feature_counts[subset_feature_counts >= MIN_CASES_PER_FEATURE].index.tolist()

    if not bip_features:
        raise ValueError(
            f"No retained features remain after applying MIN_CASES_PER_FEATURE={MIN_CASES_PER_FEATURE}."
        )

    subset_df = subset_df[[CASE_ID_COLUMN] + bip_features].copy()

    # Shortened case labels
    retained_titles = subset_df[CASE_ID_COLUMN].tolist()
    if SHORTEN_CASE_LABELS:
        short_map = make_short_titles(retained_titles, TITLE_MAX_LEN, APPEND_ID_FOR_UNIQUENESS)
    else:
        short_map = {t: t for t in retained_titles}

    # Build bipartite graph
    G_bip = nx.Graph()

    # Feature nodes
    for feat in bip_features:
        G_bip.add_node(
            f"feature::{feat}",
            label=feat,
            type="feature",
            bipartite=0,
            degree_in_subset=int(subset_feature_counts[feat]),
        )

    # Case nodes
    for full in retained_titles:
        G_bip.add_node(
            f"case::{full}",
            label=short_map.get(full, full),
            full_title=full,
            type="case",
            bipartite=1,
        )

    # Edges
    for _, row in subset_df.iterrows():
        case = str(row[CASE_ID_COLUMN])
        for feat in bip_features:
            if int(row[feat]) == 1:
                G_bip.add_edge(f"case::{case}", f"feature::{feat}", weight=1)

    out_bip_path = OUTPUT_DIR / OUT_BIP_GRAPH
    nx.write_gexf(G_bip, out_bip_path)

    # 4) Summary
    out_summary = OUTPUT_DIR / OUT_SUMMARY
    with open(out_summary, "w", encoding="utf-8") as f:
        f.write("=== Feature Absence Network Construction Summary ===\n\n")
        f.write(f"Run timestamp: {run_timestamp}\n\n")

        f.write("Inputs\n")
        f.write("------\n")
        f.write(f"Feature zero-overlap CSV: {ZERO_FEATURE_OVERLAP_CSV}\n")
        f.write(f"Incidence matrix: {INCIDENCE_PATH}\n\n")

        f.write("Selection settings\n")
        f.write("------------------\n")
        f.write(f"SIGNIFICANCE_COLUMN: {SIGNIFICANCE_COLUMN}\n")
        f.write(f"MIN_ZERO_NEIGHBORS: {MIN_ZERO_NEIGHBORS}\n")
        f.write(f"MIN_FEATURES_PER_CASE: {MIN_FEATURES_PER_CASE}\n")
        f.write(f"MIN_CASES_PER_FEATURE: {MIN_CASES_PER_FEATURE}\n")
        f.write(f"SHORTEN_CASE_LABELS: {SHORTEN_CASE_LABELS}\n")
        f.write(f"TITLE_MAX_LEN: {TITLE_MAX_LEN}\n")
        f.write(f"APPEND_ID_FOR_UNIQUENESS: {APPEND_ID_FOR_UNIQUENESS}\n\n")

        f.write("Feature absence graph\n")
        f.write("---------------------\n")
        f.write(f"Significant zero-overlap feature pairs in input table: {len(sig_df)}\n")
        f.write(f"Features retained after MIN_ZERO_NEIGHBORS filter: {len(keep_features)}\n")
        f.write(f"Edges retained: {G_abs_keep.number_of_edges()}\n\n")

        f.write("Retained bipartite graph\n")
        f.write("------------------------\n")
        f.write(f"Supporting cases retained: {len(retained_titles)}\n")
        f.write(f"Features retained in bipartite subset: {len(bip_features)}\n")
        f.write(f"Edges (case–feature links): {G_bip.number_of_edges()}\n\n")

        f.write("Interpretation\n")
        f.write("--------------\n")
        f.write("The one-mode feature absence graph shows statistically significant feature\n")
        f.write("pairs that never co-occur. The bipartite retained-subset graph shows the\n")
        f.write("cases supporting those features, making it possible to inspect the feature\n")
        f.write("regions that remain structurally disjoint across the corpus.\n\n")

        f.write("Output files\n")
        f.write("------------\n")
        f.write(f"{OUT_ABS_GRAPH}\n")
        f.write(f"{OUT_BIP_GRAPH}\n")
        f.write(f"{OUT_SUMMARY}\n")

    print("[✓] Feature absence network construction complete.")
    print(f"    Significant feature pairs used: {len(sig_df)}")
    print(f"    Retained absence features:      {len(keep_features)}")
    print(f"    Absence graph:                  {out_abs_path}")
    print(f"    Bipartite graph:                {out_bip_path}")
    print(f"    Summary:                        {out_summary}")


if __name__ == "__main__":
    main()