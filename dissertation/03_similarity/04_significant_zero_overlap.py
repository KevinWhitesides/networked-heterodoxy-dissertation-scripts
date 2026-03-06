#!/usr/bin/env python3
"""
04_significant_zero_overlap.py

Identify observed zero-overlap pairs in a binary incidence matrix and test whether
those absences are unusually strong under a degree-preserving null model.

Pipeline
--------
1) Read a binary incidence matrix from .xlsx or .csv
2) Optionally filter features by global frequency
3) Optionally filter cases by minimum number of present features
4) Identify all observed zero-overlap case pairs
5) Generate a degree-preserving null via Curveball randomization
6) Estimate empirical p(overlap = 0) for each observed zero-overlap pair
7) Apply Benjamini–Hochberg FDR correction
8) Export:
   - zero_overlap_pairs_with_significance.csv
   - analysis_summary.txt

Notes
-----
- This is the 03_similarity stage of the workflow.
- It does NOT build graphs. A later 02_networks script can consume the CSV output
  and build absence graphs or other network representations.
"""

from __future__ import annotations

import itertools
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG (edit per dataset)
# ──────────────────────────────────────────────────────────────────────────────

# Input incidence matrix (.xlsx or .csv)
INPUT_PATH = Path("input_incidence_matrix.xlsx")

# If reading Excel, which sheet to use
SHEET_NAME = 0

# Column containing case identifiers / titles
CASE_ID_COLUMN = "Source Title"

# Number of leftmost metadata columns before feature/trope columns begin.
# Example 7-book demo: 4 (Title / Author / Year / Publisher)
N_METADATA_COLS = 4

# Presence token
PRESENCE_TOKEN = "X"

# Filtering
GLOBAL_FEATURE_MIN_CASES = 2   # keep only features used by at least this many cases
MIN_FEATURES_PER_CASE = 1      # keep only cases using at least this many kept features

# Null model (Curveball) parameters
# Example dissertation-scale 2012 settings:
#   N_SAMPLES = 250
#   TRADES_BURN = 20000
#   TRADES_PER_SAMPLE = 5000
N_SAMPLES = 300
TRADES_BURN = 20000
TRADES_PER_SAMPLE = 5000
RNG_SEED = 42

# FDR thresholds to report
FDR_THRESHOLDS = [0.05, 0.01]

# Output
OUTPUT_DIR = Path(".")
OUT_CSV = "zero_overlap_pairs_with_significance.csv"
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
    """
    Convert feature columns to 0/1.
    Truthy values:
      - PRESENCE_TOKEN exactly
      - numeric values > 0
      - common truthy strings like yes / true / check / ✓ / x
    """
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


def benjamini_hochberg(pvals: Sequence[float], alpha: float) -> List[bool]:
    """Return BH/FDR significance flags for the given alpha."""
    m = len(pvals)
    if m == 0:
        return []

    order = np.argsort(pvals)
    ranked = np.array(pvals)[order]
    thresh = alpha * (np.arange(1, m + 1) / m)
    k = np.where(ranked <= thresh)[0]
    cutoff = ranked[k.max()] if k.size else -1.0
    return [(p <= cutoff and cutoff >= 0) for p in pvals]


# ──────────────────────────────────────────────────────────────────────────────
# Curveball null model
# ──────────────────────────────────────────────────────────────────────────────

def curveball_trade(a: List[int], b: List[int], rng: random.Random) -> Tuple[List[int], List[int]]:
    """
    Perform one Curveball trade between two rows represented as lists of feature IDs.
    Preserves row sums and column sums in aggregate across the matrix.
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
    """In-place Curveball trades on adjacency lists."""
    n = len(adj_lists)
    for _ in range(trades):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        adj_lists[i], adj_lists[j] = curveball_trade(adj_lists[i], adj_lists[j], rng)


def empirical_p_zero_for_pairs(
    adj_lists_init: List[List[int]],
    zero_pairs_idx: Dict[Tuple[int, int], int],
    n_features: int,
    n_samples: int,
    burn_trades: int,
    trades_per_sample: int,
    rng_seed: int,
) -> np.ndarray:
    """
    Estimate empirical p(overlap = 0) for each observed zero-overlap pair
    under a degree-preserving Curveball null model.

    Only observed zero-overlap pairs are tested.
    """
    rng = random.Random(rng_seed)

    # Work on a copy
    adj_lists = [list(sorted(x)) for x in adj_lists_init]

    # Burn-in
    run_curveball(adj_lists, burn_trades, rng)

    n_pairs = len(zero_pairs_idx)
    zero_counts = np.zeros(n_pairs, dtype=np.int32)

    for _ in range(n_samples):
        run_curveball(adj_lists, trades_per_sample, rng)

        # Build feature -> cases incidence for this sample
        feature_cases: List[List[int]] = [[] for _ in range(n_features)]
        for case_idx, feats in enumerate(adj_lists):
            for f in feats:
                feature_cases[f].append(case_idx)

        # Mark observed-zero pairs that become nonzero in this sample
        marks = np.zeros(n_pairs, dtype=bool)
        for cases in feature_cases:
            if len(cases) < 2:
                continue
            for i, j in itertools.combinations(cases, 2):
                if i > j:
                    i, j = j, i
                idx = zero_pairs_idx.get((i, j))
                if idx is not None:
                    marks[idx] = True

        # Unmarked pairs stayed at overlap == 0
        zero_counts[~marks] += 1

    return zero_counts / float(n_samples)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    random.seed(RNG_SEED)
    np.random.seed(RNG_SEED)

    df_raw = read_table(INPUT_PATH, sheet_name=SHEET_NAME)

    if CASE_ID_COLUMN not in df_raw.columns:
        raise ValueError(
            f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in input columns."
        )

    feature_cols = get_feature_columns(df_raw, N_METADATA_COLS)
    if not feature_cols:
        raise ValueError("No feature columns found. Check N_METADATA_COLS.")

    # Keep only case id + feature columns
    df = pd.concat([df_raw[[CASE_ID_COLUMN]], df_raw[feature_cols]], axis=1)

    # Binarize
    bin_features = binarize_presence(df, feature_cols, PRESENCE_TOKEN)
    df_bin = pd.concat([df[[CASE_ID_COLUMN]], bin_features], axis=1)

    # Global feature filter
    feature_freq = df_bin.drop(columns=[CASE_ID_COLUMN]).sum(axis=0)
    kept_features = feature_freq[feature_freq >= GLOBAL_FEATURE_MIN_CASES].index.tolist()
    if not kept_features:
        raise ValueError("No features remain after GLOBAL_FEATURE_MIN_CASES filter.")

    df_glob = pd.concat([df_bin[[CASE_ID_COLUMN]], df_bin[kept_features]], axis=1)

    # Case floor
    case_feature_counts = df_glob.drop(columns=[CASE_ID_COLUMN]).sum(axis=1).astype(int)
    kept_case_mask = case_feature_counts >= MIN_FEATURES_PER_CASE
    df_cases = df_glob.loc[kept_case_mask].reset_index(drop=True)

    if df_cases.empty:
        raise ValueError("No cases remain after MIN_FEATURES_PER_CASE filter.")

    case_names = df_cases[CASE_ID_COLUMN].astype(str).tolist()
    kept_feature_cols = [c for c in df_cases.columns if c != CASE_ID_COLUMN]

    # Build adjacency lists (case -> feature IDs)
    feature_index = {feat: i for i, feat in enumerate(kept_feature_cols)}
    adj_lists: List[List[int]] = []
    for _, row in df_cases.iterrows():
        present_feats = [feature_index[c] for c in kept_feature_cols if int(row[c]) == 1]
        adj_lists.append(present_feats)

    n_cases = len(adj_lists)
    n_features = len(kept_feature_cols)

    # Case-level feature counts after filtering
    case_counts_after_filter = {
        row[CASE_ID_COLUMN]: int(row[kept_feature_cols].sum())
        for _, row in df_cases.iterrows()
    }

    # Observed zero-overlap pairs
    zero_pairs: List[Tuple[int, int]] = []
    for i, j in itertools.combinations(range(n_cases), 2):
        if len(set(adj_lists[i]).intersection(adj_lists[j])) == 0:
            zero_pairs.append((i, j))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv_path = OUTPUT_DIR / OUT_CSV
    out_summary_path = OUTPUT_DIR / OUT_SUMMARY

    if not zero_pairs:
        empty_df = pd.DataFrame(
            columns=[
                "case_A",
                "case_B",
                "case_A_feature_count",
                "case_B_feature_count",
                "observed_overlap",
                "p_emp",
                *[f"sig_{alpha}" for alpha in FDR_THRESHOLDS],
            ]
        )
        empty_df.to_csv(out_csv_path, index=False, encoding="utf-8")

        with open(out_summary_path, "w", encoding="utf-8") as f:
            f.write("=== Significant Zero-Overlap Analysis Summary ===\n")
            f.write(f"Run timestamp: {run_timestamp}\n")
            f.write(f"Input file: {INPUT_PATH}\n")
            f.write(f"Cases retained after filtering: {n_cases}\n")
            f.write(f"Features retained after filtering: {n_features}\n")
            f.write("Observed zero-overlap pairs: 0\n")
            f.write(f"Null model samples: {N_SAMPLES}\n")
            f.write(f"Curveball burn-in trades: {TRADES_BURN}\n")
            f.write(f"Curveball trades per sample: {TRADES_PER_SAMPLE}\n")
            f.write(f"Random seed: {RNG_SEED}\n")

        print("No observed zero-overlap pairs after filtering.")
        print(f"Wrote empty output table: {out_csv_path}")
        print(f"Wrote analysis summary: {out_summary_path}")
        return

    # Null model significance
    zero_pairs_idx = {(i, j): k for k, (i, j) in enumerate(zero_pairs)}
    p_emp = empirical_p_zero_for_pairs(
        adj_lists_init=adj_lists,
        zero_pairs_idx=zero_pairs_idx,
        n_features=n_features,
        n_samples=N_SAMPLES,
        burn_trades=TRADES_BURN,
        trades_per_sample=TRADES_PER_SAMPLE,
        rng_seed=RNG_SEED,
    )

    # Build output table
    records = []
    for (i, j), p in zip(zero_pairs, p_emp):
        a = case_names[i]
        b = case_names[j]
        records.append(
            {
                "case_A": a,
                "case_B": b,
                "case_A_feature_count": case_counts_after_filter[a],
                "case_B_feature_count": case_counts_after_filter[b],
                "observed_overlap": 0,
                "p_emp": float(p),
            }
        )

    out_df = pd.DataFrame(records)

    # BH/FDR flags
    for alpha in FDR_THRESHOLDS:
        out_df[f"sig_{alpha}"] = benjamini_hochberg(out_df["p_emp"].tolist(), alpha)

    out_df = out_df.sort_values(["p_emp", "case_A", "case_B"]).reset_index(drop=True)
    out_df.to_csv(out_csv_path, index=False, encoding="utf-8")

    # Mandatory analysis summary
    sig_counts = {alpha: int(out_df[f"sig_{alpha}"].sum()) for alpha in FDR_THRESHOLDS}
    with open(out_summary_path, "w", encoding="utf-8") as f:
        f.write("=== Significant Zero-Overlap Analysis Summary ===\n")
        f.write(f"Run timestamp: {run_timestamp}\n")
        f.write(f"Input file: {INPUT_PATH}\n")
        f.write(f"Cases retained after filtering: {n_cases}\n")
        f.write(f"Features retained after filtering: {n_features}\n")
        f.write(f"Observed zero-overlap pairs: {len(zero_pairs)}\n")
        for alpha in FDR_THRESHOLDS:
            f.write(f"Significant zero-overlap pairs @ FDR {alpha}: {sig_counts[alpha]}\n")
        f.write(f"Null model samples: {N_SAMPLES}\n")
        f.write(f"Curveball burn-in trades: {TRADES_BURN}\n")
        f.write(f"Curveball trades per sample: {TRADES_PER_SAMPLE}\n")
        f.write(f"Random seed: {RNG_SEED}\n")

    # Console summary
    print("[✓] Significant zero-overlap analysis complete.")
    print(f"    Input: {INPUT_PATH}")
    print(f"    Cases retained: {n_cases}")
    print(f"    Features retained: {n_features}")
    print(f"    Observed zero-overlap pairs: {len(zero_pairs)}")
    for alpha in FDR_THRESHOLDS:
        print(f"    Significant pairs @ FDR {alpha}: {int(out_df[f'sig_{alpha}'].sum())}")
    print(f"    Output CSV: {out_csv_path}")
    print(f"    Analysis summary: {out_summary_path}")


if __name__ == "__main__":
    main()