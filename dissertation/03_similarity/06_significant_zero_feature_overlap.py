#!/usr/bin/env python3
"""
06_significant_zero_feature_overlap.py

Identify feature pairs that never co-occur in the same case and evaluate
whether those absences are statistically unusual under a degree-preserving
null model.

This script is the feature-level analogue of the case-level zero-overlap
analysis. It works on a binary incidence matrix where:

- rows = cases (books, songs, documents, etc.)
- columns = features (tropes, topics, entities, etc.)

For each observed zero-overlap feature pair, the script computes:

- feature_a
- count_a
- feature_b
- count_b
- cooc_count              (always 0 for retained rows)
- p_emp                   empirical probability of zero overlap under the null
- sig_0.05                Benjamini–Hochberg FDR flag at alpha = 0.05
- sig_0.01                Benjamini–Hochberg FDR flag at alpha = 0.01

Outputs:
1) zero_feature_overlap_with_significance.csv
   Full table of all observed zero-overlap feature pairs and their significance

2) analysis_summary.txt
   Human-readable run summary

Method
------
- Filters features by minimum frequency
- Identifies all observed zero-overlap feature pairs
- Randomizes the incidence matrix using Curveball trades while preserving:
    * number of features per case
    * number of cases per feature
- Estimates empirical p(overlap = 0) for each observed zero-overlap pair
- Applies Benjamini–Hochberg FDR correction
"""

from __future__ import annotations

from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import random

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

# Input dataset
INPUT_PATH = Path("input_incidence_matrix.xlsx")   # .xlsx or .csv
SHEET_NAME = 0

# Matrix structure
CASE_ID_COLUMN = "Source Title"
N_METADATA_COLS = 4
PRESENCE_TOKEN = "X"

# Feature filter
MIN_FEATURE_FREQ = 5

# Null model parameters
N_SAMPLES = 250
TRADES_BURN = 20000
TRADES_PER_SAMPLE = 5000
RNG_SEED = 42

# Output
OUTPUT_DIR = Path(".")
OUT_CSV = "zero_feature_overlap_with_significance.csv"
OUT_SUMMARY = "analysis_summary.txt"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: I/O and matrix prep
# ──────────────────────────────────────────────────────────────────────────────

def read_table(path: Path, sheet_name=0) -> pd.DataFrame:
    """Read .xlsx/.xls or .csv as strings, preserving blanks."""
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


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: BH-FDR
# ──────────────────────────────────────────────────────────────────────────────

def benjamini_hochberg(pvals: List[float], alpha: float) -> List[bool]:
    """
    Return list of significance flags under Benjamini–Hochberg FDR.
    """
    m = len(pvals)
    if m == 0:
        return []

    order = np.argsort(pvals)
    ranked = np.array(pvals, dtype=float)[order]
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = np.where(ranked <= thresh)[0]

    cutoff = ranked[passed.max()] if passed.size else -1.0
    return [(p <= cutoff and cutoff >= 0) for p in pvals]


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: Curveball randomization
# ──────────────────────────────────────────────────────────────────────────────

def curveball_trade(a: List[int], b: List[int], rng: random.Random) -> Tuple[List[int], List[int]]:
    """
    Perform one Curveball trade between two row adjacency lists.
    """
    sa, sb = set(a), set(b)
    shared = sa & sb
    ua = list(sa - shared)
    ub = list(sb - shared)

    if not ua and not ub:
        return a, b

    pool = ua + ub
    rng.shuffle(pool)

    new_a = list(shared) + pool[:len(ua)]
    new_b = list(shared) + pool[len(ua):]
    return new_a, new_b


def run_curveball(adj_lists: List[List[int]], trades: int, rng: random.Random) -> None:
    """
    In-place Curveball trades on row adjacency lists.
    """
    n = len(adj_lists)
    for _ in range(trades):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        ai, aj = adj_lists[i], adj_lists[j]
        new_ai, new_aj = curveball_trade(ai, aj, rng)
        adj_lists[i], adj_lists[j] = new_ai, new_aj


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: empirical p(overlap=0) for observed feature zero-pairs
# ──────────────────────────────────────────────────────────────────────────────

def empirical_p_zero_for_feature_pairs(
    adj_lists_init: List[List[int]],
    zero_feature_pairs_idx: Dict[Tuple[int, int], int],
    n_features: int,
    n_samples: int,
    burn_trades: int,
    trades_per_sample: int,
    rng_seed: int,
) -> np.ndarray:
    """
    Returns p_emp for each observed zero-overlap feature pair:
        p_emp = Pr(overlap(feature_i, feature_j) == 0) under a degree-preserving null
    """
    rng = random.Random(rng_seed)

    # Copy case adjacency lists (case -> list of feature IDs)
    adj_lists = [list(sorted(x)) for x in adj_lists_init]

    # Burn-in
    run_curveball(adj_lists, burn_trades, rng)

    n_pairs = len(zero_feature_pairs_idx)
    zero_counts = np.zeros(n_pairs, dtype=np.int32)

    for _ in range(n_samples):
        run_curveball(adj_lists, trades_per_sample, rng)

        # Rebuild feature -> cases incidence
        feature_cases: List[List[int]] = [[] for _ in range(n_features)]
        for case_idx, feats in enumerate(adj_lists):
            for f in feats:
                feature_cases[f].append(case_idx)

        marks = np.zeros(n_pairs, dtype=bool)

        # For each case, all feature pairs within that case co-occur in this sample
        # More efficient to iterate over case lists directly than full feature-feature matrix
        for feats in adj_lists:
            if len(feats) < 2:
                continue
            feats_sorted = sorted(feats)
            for i, j in combinations(feats_sorted, 2):
                idx = zero_feature_pairs_idx.get((i, j))
                if idx is not None:
                    marks[idx] = True

        # Unmarked observed zero-pairs remained zero in this sample
        zero_counts[~marks] += 1

    return zero_counts / float(n_samples)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Load incidence matrix ────────────────────────────────────────────────
    df_raw = read_table(INPUT_PATH, sheet_name=SHEET_NAME)

    if CASE_ID_COLUMN not in df_raw.columns:
        raise ValueError(f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in input columns.")

    case_index = df_raw.columns.get_loc(CASE_ID_COLUMN)
    if case_index >= N_METADATA_COLS:
        raise ValueError(
            f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' is outside the first {N_METADATA_COLS} columns.\n"
            "This script assumes that all metadata columns, including the case identifier, "
            "appear to the LEFT of the feature columns.\n"
            "Increase N_METADATA_COLS or rearrange the dataset so that metadata comes first."
        )

    feature_cols = get_feature_columns(df_raw, N_METADATA_COLS)
    if not feature_cols:
        raise ValueError("No feature columns found. Check N_METADATA_COLS.")

    df = pd.concat([df_raw[[CASE_ID_COLUMN]], df_raw[feature_cols]], axis=1).copy()
    bin_features = binarize_presence(df, feature_cols, PRESENCE_TOKEN)
    df_bin = pd.concat([df[[CASE_ID_COLUMN]].copy(), bin_features], axis=1)

    total_cases = len(df_bin)

    # ─── Feature frequency filter ─────────────────────────────────────────────
    feature_counts_all = df_bin.drop(columns=[CASE_ID_COLUMN]).sum(axis=0).astype(int)
    keep_features = feature_counts_all[feature_counts_all >= MIN_FEATURE_FREQ].index.tolist()

    if len(keep_features) < 2:
        raise ValueError(
            f"Only {len(keep_features)} features remain after MIN_FEATURE_FREQ={MIN_FEATURE_FREQ}. "
            "Need at least 2."
        )

    sub_df = df_bin[[CASE_ID_COLUMN] + keep_features].copy()
    X = sub_df[keep_features].to_numpy(dtype=np.uint8)

    feature_counts = sub_df[keep_features].sum(axis=0).astype(int)
    feature_names = list(feature_counts.index)
    counts_arr = feature_counts.values
    n_features = len(feature_names)

    # ─── Build co-occurrence matrix and identify observed zero-overlap pairs ──
    cooc = X.T @ X   # feature × feature raw overlap counts
    np.fill_diagonal(cooc, 0)

    zero_pairs: List[Tuple[int, int]] = []
    for i in range(n_features - 1):
        for j in range(i + 1, n_features):
            if cooc[i, j] == 0:
                zero_pairs.append((i, j))

    if not zero_pairs:
        empty_df = pd.DataFrame(columns=[
            "feature_a", "count_a", "feature_b", "count_b",
            "cooc_count", "p_emp", "sig_0.05", "sig_0.01"
        ])
        empty_df.to_csv(OUTPUT_DIR / OUT_CSV, index=False, encoding="utf-8")

        with open(OUTPUT_DIR / OUT_SUMMARY, "w", encoding="utf-8") as f:
            f.write("=== Significant Zero Feature Overlap Summary ===\n\n")
            f.write(f"Run timestamp: {run_timestamp}\n\n")
            f.write("No observed zero-overlap feature pairs were found after filtering.\n")

        print("No observed zero-overlap feature pairs found after filtering.")
        return

    # ─── Build case adjacency lists for Curveball randomization ───────────────
    # case -> list of feature ids
    adj_lists: List[List[int]] = []
    for row in X:
        feats = list(np.where(row == 1)[0])
        adj_lists.append(feats)

    # Map observed zero-pairs to indices for fast lookup
    zero_pairs_idx = {pair: idx for idx, pair in enumerate(zero_pairs)}

    # ─── Empirical p(overlap = 0) under degree-preserving null ────────────────
    print(f"Observed zero-overlap feature pairs: {len(zero_pairs):,}")
    print(
        "Running degree-preserving null model "
        f"(samples={N_SAMPLES}, burn={TRADES_BURN}, trades/sample={TRADES_PER_SAMPLE}) ..."
    )

    p_emp = empirical_p_zero_for_feature_pairs(
        adj_lists_init=adj_lists,
        zero_feature_pairs_idx=zero_pairs_idx,
        n_features=n_features,
        n_samples=N_SAMPLES,
        burn_trades=TRADES_BURN,
        trades_per_sample=TRADES_PER_SAMPLE,
        rng_seed=RNG_SEED,
    )

    # ─── Assemble results table ───────────────────────────────────────────────
    records = []
    for (i, j), p in zip(zero_pairs, p_emp):
        records.append({
            "feature_a": feature_names[i],
            "count_a": int(counts_arr[i]),
            "feature_b": feature_names[j],
            "count_b": int(counts_arr[j]),
            "cooc_count": 0,
            "p_emp": float(p),
        })

    out_df = pd.DataFrame(records)

    # BH-FDR
    out_df["sig_0.05"] = benjamini_hochberg(out_df["p_emp"].tolist(), 0.05)
    out_df["sig_0.01"] = benjamini_hochberg(out_df["p_emp"].tolist(), 0.01)

    # Sort most interesting pairs first: lowest p_emp, then highest counts
    out_df = out_df.sort_values(
        by=["p_emp", "count_a", "count_b", "feature_a", "feature_b"],
        ascending=[True, False, False, True, True]
    ).reset_index(drop=True)

    out_csv_path = OUTPUT_DIR / OUT_CSV
    out_df.to_csv(out_csv_path, index=False, encoding="utf-8")

    # ─── Summary ──────────────────────────────────────────────────────────────
    sig_005_n = int(out_df["sig_0.05"].sum())
    sig_001_n = int(out_df["sig_0.01"].sum())
    total_possible = n_features * (n_features - 1) // 2

    with open(OUTPUT_DIR / OUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write("=== Significant Zero Feature Overlap Summary ===\n\n")
        f.write(f"Run timestamp: {run_timestamp}\n\n")

        f.write("Input\n")
        f.write("-----\n")
        f.write(f"Dataset: {INPUT_PATH}\n")
        f.write(f"Case ID column: {CASE_ID_COLUMN}\n")
        f.write(f"Metadata columns assumed on the left: {N_METADATA_COLS}\n")
        f.write(f"Presence token: {PRESENCE_TOKEN}\n\n")

        f.write("Filtering\n")
        f.write("---------\n")
        f.write(f"MIN_FEATURE_FREQ: {MIN_FEATURE_FREQ}\n\n")

        f.write("Corpus statistics\n")
        f.write("-----------------\n")
        f.write(f"Total cases: {total_cases}\n")
        f.write(f"Features before filtering: {len(feature_cols)}\n")
        f.write(f"Features after filtering: {n_features}\n")
        f.write(f"Total possible feature pairs after filtering: {total_possible:,}\n")
        f.write(f"Observed zero-overlap feature pairs: {len(out_df):,}\n\n")

        f.write("Null model\n")
        f.write("----------\n")
        f.write(f"N_SAMPLES: {N_SAMPLES}\n")
        f.write(f"TRADES_BURN: {TRADES_BURN}\n")
        f.write(f"TRADES_PER_SAMPLE: {TRADES_PER_SAMPLE}\n")
        f.write(f"RNG_SEED: {RNG_SEED}\n\n")

        f.write("Significance results\n")
        f.write("--------------------\n")
        f.write(f"Pairs significant at FDR 0.05: {sig_005_n}\n")
        f.write(f"Pairs significant at FDR 0.01: {sig_001_n}\n\n")

        f.write("Interpretation\n")
        f.write("--------------\n")
        f.write("Each row in the output CSV is a feature pair that never co-occurs in the same case.\n")
        f.write("The p_emp column gives the empirical probability of observing zero overlap under\n")
        f.write("a degree-preserving null model. Lower p_emp values indicate more surprising absences.\n")
        f.write("The sig_0.05 and sig_0.01 columns provide Benjamini–Hochberg FDR flags.\n\n")

        f.write("Suggested sorting workflow\n")
        f.write("--------------------------\n")
        f.write("Sort by p_emp (ascending)\n")
        f.write("    → identifies the most statistically surprising feature disjunctions\n\n")
        f.write("Sort by count_a and count_b (descending)\n")
        f.write("    → highlights disjoint feature pairs that are individually common in the corpus\n\n")

        f.write("Output files\n")
        f.write("------------\n")
        f.write(f"{OUT_CSV}\n")
        f.write(f"{OUT_SUMMARY}\n")

    # ─── Console summary ──────────────────────────────────────────────────────
    print("[✓] Significant zero feature overlap analysis complete.")
    print(f"    Input dataset:      {INPUT_PATH}")
    print(f"    Total cases:        {total_cases}")
    print(f"    Features analyzed:  {n_features}")
    print(f"    Zero-overlap pairs: {len(out_df):,}")
    print(f"    FDR 0.05 sig pairs: {sig_005_n}")
    print(f"    FDR 0.01 sig pairs: {sig_001_n}")
    print(f"    Main output:        {out_csv_path}")
    print(f"    Summary:            {OUTPUT_DIR / OUT_SUMMARY}")


if __name__ == "__main__":
    main()