#!/usr/bin/env python3
"""
03_build_case_absence_networks.py

Build network outputs from a master zero-overlap significance table produced by
03_similarity/04_significant_zero_case_overlap.py.

This script creates:

1) absence_graph_sig.gexf
   - case × case graph
   - edges = statistically significant zero-overlap relationships

2) bipartite_thr2.gexf
   - case × trope bipartite graph for the retained absence subset
   - keeps only tropes appearing in at least BIPARTITE_TROPE_MIN_CASES retained cases

3) analysis_summary.txt
   - compact human-readable record of inputs, thresholds, retained counts,
     and network statistics

Typical workflow
----------------
1) Run the significance script (04_significant_zero_case_overlap.py) first to produce:
      zero_overlap_pairs_with_significance.csv
2) Run this script to build network representations from that table.

Inputs
------
- zero-overlap significance CSV
- original binary incidence matrix (.xlsx or .csv)

This script does NOT perform significance testing itself.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd
import networkx as nx


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG (edit per dataset)
# ──────────────────────────────────────────────────────────────────────────────

# Input files
ZERO_OVERLAP_CSV = Path("zero_overlap_pairs_with_significance.csv")
INPUT_PATH = Path("input_incidence_matrix.xlsx")   # .xlsx or .csv
SHEET_NAME = 0

# Column containing case identifiers / titles in the incidence matrix
CASE_ID_COLUMN = "Source Title"

# Number of metadata columns before feature/trope columns begin
# Example 7-book demo: 4 (Title / Author / Year / Publisher)
N_METADATA_COLS = 4

# Presence token in the incidence matrix
PRESENCE_TOKEN = "X"

# Which significance column in ZERO_OVERLAP_CSV determines edges in the absence graph
# e.g. "sig_0.05" or "sig_0.01"
SIGNIFICANCE_COLUMN = "sig_0.05"

# Keep only cases with at least this many significant-zero neighbors
MIN_ZERO_NEIGHBORS = 2

# Bipartite graph feature threshold within the retained subset
BIPARTITE_TROPE_MIN_CASES = 2

# Optional short labels for case nodes in the bipartite GEXF
SHORTEN_CASE_LABELS = True
TITLE_MAX_LEN = 36
APPEND_ID_FOR_UNIQUENESS = True

# Output
OUTPUT_DIR = Path(".")
OUT_ABS_GEXF = "absence_graph_sig.gexf"
OUT_BIP_GEXF = "bipartite_thr2.gexf"
OUT_SUMMARY = "analysis_summary.txt"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def read_table(path: Path, sheet_name=0) -> pd.DataFrame:
    """Read .xlsx/.xls or .csv as strings, preserving blanks."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=str, keep_default_na=False)
    elif suffix == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported input format: {suffix}. Use .xlsx/.xls or .csv.")

    df.columns = df.columns.map(str)
    return df


def get_feature_columns(df: pd.DataFrame, n_metadata_cols: int) -> List[str]:
    """Assume feature columns begin after the first n_metadata_cols columns."""
    if n_metadata_cols < 0 or n_metadata_cols >= df.shape[1]:
        raise ValueError(
            f"N_METADATA_COLS={n_metadata_cols} invalid for table with {df.shape[1]} columns."
        )
    return list(df.columns[n_metadata_cols:])


def binarize_presence(df: pd.DataFrame, feature_cols: Sequence[str], token: str) -> pd.DataFrame:
    """Convert feature columns to 0/1."""
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


def make_short_titles(titles: List[str], max_len: int, append_id: bool) -> Dict[str, str]:
    """Produce shortened display labels for long case titles."""
    mapping: Dict[str, str] = {}
    seen = set()

    for idx, full in enumerate(titles, start=1):
        t = " ".join(str(full).split()).strip()

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
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ─── 1) Read and validate zero-overlap significance table ─────────────────
    if not ZERO_OVERLAP_CSV.exists():
        raise FileNotFoundError(f"Zero-overlap CSV not found: {ZERO_OVERLAP_CSV}")

    pairs_df = pd.read_csv(ZERO_OVERLAP_CSV)

    required_cols = {"case_A", "case_B", "p_emp", SIGNIFICANCE_COLUMN}
    missing = required_cols - set(pairs_df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns in {ZERO_OVERLAP_CSV}: {sorted(missing)}"
        )

    # Keep only significant pairs according to the chosen significance column
    sig_df = pairs_df[pairs_df[SIGNIFICANCE_COLUMN].astype(bool)].copy()

    # Build initial absence graph from significant pairs
    G_abs = nx.Graph()
    for _, row in sig_df.iterrows():
        a = str(row["case_A"])
        b = str(row["case_B"])
        G_abs.add_edge(a, b, p_emp=float(row["p_emp"]))

    # Apply minimum-neighbor filter
    keep_cases = {n for n, d in G_abs.degree() if d >= MIN_ZERO_NEIGHBORS}
    G_abs = G_abs.subgraph(keep_cases).copy()

    # Write absence graph
    abs_gexf_path = OUTPUT_DIR / OUT_ABS_GEXF
    nx.write_gexf(G_abs, abs_gexf_path)

    # ─── 2) Read original incidence matrix ────────────────────────────────────
    df_raw = read_table(INPUT_PATH, sheet_name=SHEET_NAME)

    if CASE_ID_COLUMN not in df_raw.columns:
        raise ValueError(
            f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in incidence matrix."
        )

    feature_cols = get_feature_columns(df_raw, N_METADATA_COLS)
    if not feature_cols:
        raise ValueError("No feature columns found. Check N_METADATA_COLS.")

    # Keep only case id + feature columns
    df = pd.concat([df_raw[[CASE_ID_COLUMN]], df_raw[feature_cols]], axis=1)

    # Binarize
    bin_features = binarize_presence(df, feature_cols, PRESENCE_TOKEN)
    df_bin = pd.concat([df[[CASE_ID_COLUMN]], bin_features], axis=1)

    # Retain only cases appearing in the filtered absence graph
    retained_df = df_bin[df_bin[CASE_ID_COLUMN].astype(str).isin(keep_cases)].copy().reset_index(drop=True)

    # ─── 3) Build bipartite graph for retained subset ─────────────────────────
    # Threshold tropes by number of retained cases they appear in
    retained_feature_cols = [c for c in retained_df.columns if c != CASE_ID_COLUMN]
    if retained_df.empty:
        trope_freq = pd.Series(dtype=int)
        keep_tropes = []
    else:
        trope_freq = retained_df[retained_feature_cols].sum(axis=0)
        keep_tropes = trope_freq[trope_freq >= BIPARTITE_TROPE_MIN_CASES].index.tolist()

    G_bip = nx.Graph()

    retained_titles = retained_df[CASE_ID_COLUMN].astype(str).tolist()
    if SHORTEN_CASE_LABELS:
        short_map = make_short_titles(
            retained_titles,
            max_len=TITLE_MAX_LEN,
            append_id=APPEND_ID_FOR_UNIQUENESS,
        )
    else:
        short_map = {t: t for t in retained_titles}

    # Add case nodes
    for full in retained_titles:
        G_bip.add_node(
            f"case::{full}",
            label=short_map.get(full, full),
            full_title=full,
            type="case",
            bipartite=0,
        )

    # Add trope nodes
    for trope in keep_tropes:
        G_bip.add_node(
            f"trope::{trope}",
            label=trope,
            type="trope",
            bipartite=1,
            degree_in_retained_subset=int(trope_freq[trope]),
        )

    # Add case–trope incidence edges
    for _, row in retained_df.iterrows():
        case = str(row[CASE_ID_COLUMN])
        for trope in keep_tropes:
            if int(row[trope]) == 1:
                G_bip.add_edge(f"case::{case}", f"trope::{trope}", weight=1)

    bip_gexf_path = OUTPUT_DIR / OUT_BIP_GEXF
    nx.write_gexf(G_bip, bip_gexf_path)

    # ─── 4) Write mandatory analysis summary ──────────────────────────────────
    with open(OUTPUT_DIR / OUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write("=== Absence Network Construction Summary ===\n\n")
        f.write(f"Run timestamp: {run_timestamp}\n\n")

        f.write("Input files\n")
        f.write("-----------\n")
        f.write(f"Zero-overlap significance table:\n    {ZERO_OVERLAP_CSV}\n\n")
        f.write(f"Original incidence matrix:\n    {INPUT_PATH}\n\n")

        f.write("Filtering parameters\n")
        f.write("--------------------\n")
        f.write(f"Significance column used: {SIGNIFICANCE_COLUMN}\n")
        f.write(f"Minimum significant-zero neighbors required: {MIN_ZERO_NEIGHBORS}\n")
        f.write(f"Trope frequency threshold for bipartite graph: ≥{BIPARTITE_TROPE_MIN_CASES}\n\n")

        f.write("Network statistics\n")
        f.write("------------------\n")
        f.write(f"Books appearing in significant-zero pairs (before neighbor filter): {len(set(sig_df['case_A']).union(sig_df['case_B']))}\n")
        f.write(f"Books retained in absence graph: {G_abs.number_of_nodes()}\n")
        f.write(f"Edges in absence graph: {G_abs.number_of_edges()}\n\n")

        f.write("Bipartite network (threshold ≥2 tropes)\n")
        f.write("---------------------------------------\n")
        f.write(f"Books retained: {len(retained_titles)}\n")
        f.write(f"Tropes retained: {len(keep_tropes)}\n")
        f.write(f"Edges (case–trope links): {G_bip.number_of_edges()}\n\n")

        f.write("Output files\n")
        f.write("------------\n")
        f.write(f"{OUT_ABS_GEXF}\n")
        f.write(f"{OUT_BIP_GEXF}\n")
        f.write(f"{OUT_SUMMARY}\n")

    # ─── 5) Console summary ───────────────────────────────────────────────────
    print("[✓] Absence network construction complete.")
    print(f"    Zero-overlap table: {ZERO_OVERLAP_CSV}")
    print(f"    Incidence matrix:   {INPUT_PATH}")
    print(f"    Significance col:   {SIGNIFICANCE_COLUMN}")
    print(f"    Min zero-neighbors: {MIN_ZERO_NEIGHBORS}")
    print(f"    Absence graph:      {G_abs.number_of_nodes()} nodes | {G_abs.number_of_edges()} edges")
    print(f"    Bipartite graph:    {len(retained_titles)} cases | {len(keep_tropes)} tropes | {G_bip.number_of_edges()} edges")
    print(f"    Wrote:              {abs_gexf_path}")
    print(f"    Wrote:              {bip_gexf_path}")
    print(f"    Wrote:              {OUTPUT_DIR / OUT_SUMMARY}")


if __name__ == "__main__":
    main()