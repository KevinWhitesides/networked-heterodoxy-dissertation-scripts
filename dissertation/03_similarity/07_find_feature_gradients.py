#!/usr/bin/env python3
"""
07_find_feature_gradients.py

Find feature gradients between zero-overlap endpoint pairs using a binary
incidence matrix and the output of:

    06_significant_zero_feature_overlap.py

A feature gradient is a chain such as:

    Feature A -> Feature B -> Feature C -> Feature D -> Feature E

such that:
- A and E never co-occur in the same case
- adjacent features do co-occur
- the chain moves gradually from A's case-distribution toward E's

This script supports:

Endpoint selection modes
------------------------
1) all
   Use all zero-overlap feature pairs from the feature zero-overlap CSV

2) significant
   Use only feature pairs passing a chosen significance column
   (e.g. sig_0.05)

3) specific
   Use one user-specified zero-overlap feature pair only

Chain length modes
------------------
1) fixed
   Search only one exact chain length

2) range
   Search across a bounded range of chain lengths

Search modes
------------
1) strict
   Requires:
   - minimum adjacent Jaccard
   - optional minimum adjacent co-occurrence count
   - strict monotone decrease in similarity to A
   - strict monotone increase in similarity to E
   - neighborhood dominance

2) ranked
   Requires only:
   - minimum adjacent Jaccard
   - optional minimum adjacent co-occurrence count

   Then scores candidate chains by:
   - adjacency strength
   - monotonicity quality
   - positional smoothness

Outputs
-------
1) feature_gradients.csv
   One row per retained chain, with endpoint pair, chain members,
   adjacent similarities/co-occurrences, and score fields.

2) analysis_summary.txt
   Human-readable record of inputs, settings, and results.
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

# Inputs
ZERO_FEATURE_OVERLAP_CSV = Path("zero_feature_overlap_with_significance.csv")
INCIDENCE_PATH = Path("input_incidence_matrix.xlsx")   # .xlsx or .csv
SHEET_NAME = 0

# Matrix structure
CASE_ID_COLUMN = "Source Title"
N_METADATA_COLS = 4
PRESENCE_TOKEN = "X"

# Feature frequency filter (should generally match or exceed the earlier script)
MIN_FEATURE_FREQ = 5

# Endpoint selection
ENDPOINT_MODE = "significant"     # "all", "significant", or "specific"
SIGNIFICANCE_COLUMN = "sig_0.05"  # used only if ENDPOINT_MODE = "significant"

# Used only if ENDPOINT_MODE = "specific"
SPECIFIC_FEATURE_A = ""
SPECIFIC_FEATURE_E = ""

# Chain length
CHAIN_LENGTH_MODE = "fixed"       # "fixed" or "range"
CHAIN_LENGTH = 5                  # used only if CHAIN_LENGTH_MODE = "fixed"
MIN_CHAIN_LENGTH = 4              # used only if CHAIN_LENGTH_MODE = "range"
MAX_CHAIN_LENGTH = 6              # used only if CHAIN_LENGTH_MODE = "range"

# Search mode
SEARCH_MODE = "ranked"            # "strict" or "ranked"

# Adjacency requirements for neighboring features in the chain
MIN_ADJ_JACCARD = 0.05
MIN_ADJ_COOCC = 2

# Beam search / output
BEAM_WIDTH = 20
TOP_RESULTS_PER_ENDPOINT = 10
TOP_RESULTS_TOTAL = 100

# Numerical tolerance
EPS = 1e-9

# Output
OUTPUT_DIR = Path(".")
OUT_CSV = "feature_gradients.csv"
OUT_SUMMARY = "analysis_summary.txt"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: I/O and matrix prep
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


def normalize_pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: feature-space similarity
# ──────────────────────────────────────────────────────────────────────────────

def build_feature_similarity(X: np.ndarray, feature_names: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    From case × feature matrix X, build:
    - feature × feature Jaccard matrix
    - feature × feature co-occurrence count matrix
    """
    n_features = X.shape[1]
    cooc = X.T @ X
    cooc = cooc.astype(int)

    jmat = np.zeros((n_features, n_features), dtype=float)
    counts = X.sum(axis=0).astype(int)

    for i in range(n_features):
        for j in range(i, n_features):
            inter = int(cooc[i, j])
            union = int(counts[i] + counts[j] - inter)
            j = float(inter / union) if union > 0 else 0.0
            jmat[i, j] = j
            jmat[j, i] = j

    jmat_df = pd.DataFrame(jmat, index=feature_names, columns=feature_names)
    cooc_df = pd.DataFrame(cooc, index=feature_names, columns=feature_names)
    return jmat_df, cooc_df


def t_coord_all(feature_order: List[str], jmat_df: pd.DataFrame, a: str, e: str) -> pd.Series:
    """
    Projection coordinate:
        t(x) = (J(x,A) - J(x,E)) / (J(x,A) + J(x,E))
    """
    sA = jmat_df.loc[feature_order, a]
    sE = jmat_df.loc[feature_order, e]
    return (sA - sE) / (sA + sE + 1e-12)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: chain evaluation
# ──────────────────────────────────────────────────────────────────────────────

def adjacency_passes(chain: List[str], jmat_df: pd.DataFrame, cooc_df: pd.DataFrame) -> bool:
    """
    Hard adjacency requirements used in both strict and ranked modes.
    """
    for u, v in zip(chain[:-1], chain[1:]):
        if float(jmat_df.loc[u, v]) + EPS < MIN_ADJ_JACCARD:
            return False
        if MIN_ADJ_COOCC > 0 and int(cooc_df.loc[u, v]) < MIN_ADJ_COOCC:
            return False
    return True


def strict_gradient_ok(chain: List[str], jmat_df: pd.DataFrame) -> bool:
    """
    Strict mode:
    - similarity to A strictly decreases
    - similarity to E strictly increases
    - neighborhood dominance
    """
    A = chain[0]
    E = chain[-1]

    sA = [float(jmat_df.loc[x, A]) for x in chain]
    sE = [float(jmat_df.loc[x, E]) for x in chain]

    if not all(sA[k] > sA[k + 1] + EPS for k in range(len(chain) - 1)):
        return False

    if not all(sE[k] + EPS < sE[k + 1] for k in range(len(chain) - 1)):
        return False

    m = len(chain)
    for i in range(m):
        prev = None
        for d in range(1, m):
            j = i + d
            if j >= m:
                break
            val = float(jmat_df.loc[chain[i], chain[j]])
            if prev is not None and not (prev > val + EPS):
                return False
            prev = val

    return True


def ranked_chain_score(chain: List[str], jmat_df: pd.DataFrame, t_map: pd.Series) -> Dict[str, float]:
    """
    Ranked mode score components:
    - adjacency strength
    - monotonicity penalties
    - positional smoothness penalty

    Higher total_score is better.
    """
    A = chain[0]
    E = chain[-1]
    m = len(chain)

    adj_js = [float(jmat_df.loc[u, v]) for u, v in zip(chain[:-1], chain[1:])]
    min_adj = min(adj_js)
    adj_sum = sum(adj_js)

    sA = [float(jmat_df.loc[x, A]) for x in chain]
    sE = [float(jmat_df.loc[x, E]) for x in chain]

    mono_A_viol = 0
    mono_E_viol = 0
    mono_A_mag = 0.0
    mono_E_mag = 0.0

    for k in range(m - 1):
        if not (sA[k] > sA[k + 1] + EPS):
            mono_A_viol += 1
            mono_A_mag += max(0.0, sA[k + 1] - sA[k])

        if not (sE[k] + EPS < sE[k + 1]):
            mono_E_viol += 1
            mono_E_mag += max(0.0, sE[k] - sE[k + 1])

    if m <= 2:
        smooth_penalty = 0.0
    else:
        targets = np.linspace(1, -1, m)[1:-1]
        actuals = np.array([float(t_map.loc[x]) for x in chain[1:-1]])
        smooth_penalty = float(np.abs(actuals - targets).sum())

    total_score = (
        (2.0 * min_adj) +
        (1.0 * adj_sum) -
        (2.0 * mono_A_viol) -
        (2.0 * mono_E_viol) -
        (5.0 * mono_A_mag) -
        (5.0 * mono_E_mag) -
        (1.0 * smooth_penalty)
    )

    return {
        "min_adj": round(min_adj, 6),
        "adj_sum": round(adj_sum, 6),
        "mono_A_viol": mono_A_viol,
        "mono_E_viol": mono_E_viol,
        "mono_A_mag": round(mono_A_mag, 6),
        "mono_E_mag": round(mono_E_mag, 6),
        "smooth_penalty": round(smooth_penalty, 6),
        "total_score": round(total_score, 6),
    }


def chain_to_record(
    chain: List[str],
    endpoint_mode: str,
    sig_col: str,
    search_mode: str,
    jmat_df: pd.DataFrame,
    cooc_df: pd.DataFrame,
    t_map: pd.Series,
) -> Dict[str, object]:
    record: Dict[str, object] = {
        "endpoint_mode": endpoint_mode,
        "search_mode": search_mode,
        "significance_column": sig_col if endpoint_mode == "significant" else "",
        "feature_A": chain[0],
        "feature_E": chain[-1],
        "chain_length": len(chain),
        "chain": " | ".join(chain),
    }

    for idx, feat in enumerate(chain, start=1):
        record[f"feature_{idx}"] = feat

    adj_pairs = list(zip(chain[:-1], chain[1:]))
    for idx, (u, v) in enumerate(adj_pairs, start=1):
        record[f"adj_{idx}_pair"] = f"{u} -> {v}"
        record[f"adj_{idx}_jaccard"] = round(float(jmat_df.loc[u, v]), 6)
        record[f"adj_{idx}_cooc"] = int(cooc_df.loc[u, v])

    sA = [round(float(jmat_df.loc[x, chain[0]]), 6) for x in chain]
    sE = [round(float(jmat_df.loc[x, chain[-1]]), 6) for x in chain]
    record["sim_to_A_seq"] = str(sA)
    record["sim_to_E_seq"] = str(sE)

    if len(chain) > 2:
        record["interior_t_seq"] = str([round(float(t_map.loc[x]), 6) for x in chain[1:-1]])
    else:
        record["interior_t_seq"] = "[]"

    record["strict_pass"] = strict_gradient_ok(chain, jmat_df)
    record.update(ranked_chain_score(chain, jmat_df, t_map))

    return record


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Load feature zero-overlap table ──────────────────────────────────────
    if not ZERO_FEATURE_OVERLAP_CSV.exists():
        raise FileNotFoundError(f"Feature zero-overlap CSV not found: {ZERO_FEATURE_OVERLAP_CSV}")

    zero_df = pd.read_csv(ZERO_FEATURE_OVERLAP_CSV)

    required_cols = {"feature_a", "feature_b"}
    if not required_cols.issubset(zero_df.columns):
        raise ValueError(
            f"{ZERO_FEATURE_OVERLAP_CSV} must contain columns: {sorted(required_cols)}"
        )

    zero_df[["feature_a", "feature_b"]] = zero_df[["feature_a", "feature_b"]].astype(str)

    # ─── Load incidence matrix and build feature-space similarity ─────────────
    df_raw = read_table(INCIDENCE_PATH, sheet_name=SHEET_NAME)

    if CASE_ID_COLUMN not in df_raw.columns:
        raise ValueError(f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in input columns.")

    case_index = df_raw.columns.get_loc(CASE_ID_COLUMN)
    if case_index >= N_METADATA_COLS:
        raise ValueError(
            f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' is outside the first {N_METADATA_COLS} columns.\n"
            "This script assumes that all metadata columns, including the case identifier, "
            "appear to the LEFT of the feature columns."
        )

    feature_cols_all = get_feature_columns(df_raw, N_METADATA_COLS)
    if not feature_cols_all:
        raise ValueError("No feature columns found. Check N_METADATA_COLS.")

    df = pd.concat([df_raw[[CASE_ID_COLUMN]], df_raw[feature_cols_all]], axis=1).copy()
    bin_features = binarize_presence(df, feature_cols_all, PRESENCE_TOKEN)
    df_bin = pd.concat([df[[CASE_ID_COLUMN]].copy(), bin_features], axis=1)

    # Feature frequency filter
    feature_counts_all = df_bin.drop(columns=[CASE_ID_COLUMN]).sum(axis=0).astype(int)
    keep_features = feature_counts_all[feature_counts_all >= MIN_FEATURE_FREQ].index.tolist()

    if len(keep_features) < 2:
        raise ValueError(
            f"Only {len(keep_features)} features remain after MIN_FEATURE_FREQ={MIN_FEATURE_FREQ}. "
            "Need at least 2."
        )

    X = df_bin[keep_features].to_numpy(dtype=np.uint8)
    feature_order = keep_features

    jmat_df, cooc_df = build_feature_similarity(X, feature_order)

    # ─── Endpoint selection ───────────────────────────────────────────────────
    if ENDPOINT_MODE not in {"all", "significant", "specific"}:
        raise ValueError("ENDPOINT_MODE must be 'all', 'significant', or 'specific'.")

    if ENDPOINT_MODE == "all":
        endpoint_df = zero_df.copy()

    elif ENDPOINT_MODE == "significant":
        if SIGNIFICANCE_COLUMN not in zero_df.columns:
            raise ValueError(
                f"SIGNIFICANCE_COLUMN '{SIGNIFICANCE_COLUMN}' not found in {ZERO_FEATURE_OVERLAP_CSV}"
            )
        endpoint_df = zero_df[zero_df[SIGNIFICANCE_COLUMN].astype(bool)].copy()

    else:  # specific
        if not SPECIFIC_FEATURE_A or not SPECIFIC_FEATURE_E:
            raise ValueError(
                "For ENDPOINT_MODE='specific', set both SPECIFIC_FEATURE_A and SPECIFIC_FEATURE_E."
            )

        a, e = normalize_pair(str(SPECIFIC_FEATURE_A), str(SPECIFIC_FEATURE_E))
        pair_mask = (
            zero_df.apply(lambda r: normalize_pair(str(r["feature_a"]), str(r["feature_b"])), axis=1) == (a, e)
        )
        endpoint_df = zero_df[pair_mask].copy()

        if endpoint_df.empty:
            raise ValueError(
                f"The specified pair ({SPECIFIC_FEATURE_A}, {SPECIFIC_FEATURE_E}) was not found "
                "in the feature zero-overlap table."
            )

    # Keep only endpoints that still exist after MIN_FEATURE_FREQ filtering
    endpoint_pairs = []
    seen_pairs = set()

    for _, row in endpoint_df.iterrows():
        a, e = normalize_pair(str(row["feature_a"]), str(row["feature_b"]))
        if a not in feature_order or e not in feature_order:
            continue
        if int(cooc_df.loc[a, e]) != 0:
            continue
        if (a, e) not in seen_pairs:
            seen_pairs.add((a, e))
            endpoint_pairs.append((a, e))

    if not endpoint_pairs:
        raise ValueError("No valid zero-overlap feature endpoint pairs remained after filtering.")

    # ─── Chain lengths ────────────────────────────────────────────────────────
    if CHAIN_LENGTH_MODE not in {"fixed", "range"}:
        raise ValueError("CHAIN_LENGTH_MODE must be 'fixed' or 'range'.")

    if CHAIN_LENGTH_MODE == "fixed":
        chain_lengths = [CHAIN_LENGTH]
    else:
        chain_lengths = list(range(MIN_CHAIN_LENGTH, MAX_CHAIN_LENGTH + 1))

    if min(chain_lengths) < 3:
        raise ValueError("Minimum chain length must be at least 3.")
    if max(chain_lengths) > len(feature_order):
        raise ValueError("Chain length exceeds number of available features.")

    # ─── Search ───────────────────────────────────────────────────────────────
    all_records: List[Dict[str, object]] = []
    discard_adj = 0
    discard_strict = 0
    endpoint_with_results = 0

    for a, e in endpoint_pairs:
        t_map = t_coord_all(feature_order, jmat_df, a, e)
        pool_feats = [f for f in feature_order if f not in (a, e)]

        endpoint_records: List[Dict[str, object]] = []

        for chain_len in chain_lengths:
            n_interior = chain_len - 2
            if n_interior <= 0:
                continue

            targets = np.linspace(1, -1, chain_len)[1:-1]

            beams: List[List[str]] = []
            for tgt in targets:
                ranked_feats = sorted(
                    pool_feats,
                    key=lambda f: (
                        abs(float(t_map.loc[f]) - tgt),
                        -float(jmat_df.loc[f, a]),
                        float(jmat_df.loc[f, e]),
                    )
                )
                beams.append(ranked_feats[:BEAM_WIDTH])

            def recurse_build(pos: int, partial: List[str]) -> None:
                nonlocal discard_adj, discard_strict, endpoint_records

                if pos == len(beams):
                    chain = [a] + partial + [e]

                    if len(set(chain)) != len(chain):
                        return

                    if not adjacency_passes(chain, jmat_df, cooc_df):
                        discard_adj += 1
                        return

                    if SEARCH_MODE == "strict":
                        if not strict_gradient_ok(chain, jmat_df):
                            discard_strict += 1
                            return

                    record = chain_to_record(
                        chain=chain,
                        endpoint_mode=ENDPOINT_MODE,
                        sig_col=SIGNIFICANCE_COLUMN,
                        search_mode=SEARCH_MODE,
                        jmat_df=jmat_df,
                        cooc_df=cooc_df,
                        t_map=t_map,
                    )
                    endpoint_records.append(record)
                    return

                for candidate in beams[pos]:
                    if candidate in partial or candidate in (a, e):
                        continue
                    recurse_build(pos + 1, partial + [candidate])

            recurse_build(0, [])

        if endpoint_records:
            endpoint_with_results += 1
            endpoint_df_rec = pd.DataFrame(endpoint_records)

            if SEARCH_MODE == "strict":
                endpoint_df_rec = endpoint_df_rec.sort_values(
                    by=["min_adj", "adj_sum"],
                    ascending=[False, False]
                )
            else:
                endpoint_df_rec = endpoint_df_rec.sort_values(
                    by=["total_score", "min_adj", "adj_sum"],
                    ascending=[False, False, False]
                )

            endpoint_df_rec = endpoint_df_rec.head(TOP_RESULTS_PER_ENDPOINT)
            all_records.extend(endpoint_df_rec.to_dict(orient="records"))

    # ─── Output ───────────────────────────────────────────────────────────────
    out_csv_path = OUTPUT_DIR / OUT_CSV
    out_summary_path = OUTPUT_DIR / OUT_SUMMARY

    if not all_records:
        empty_df = pd.DataFrame(columns=[
            "endpoint_mode", "search_mode", "significance_column",
            "feature_A", "feature_E", "chain_length", "chain", "strict_pass",
            "min_adj", "adj_sum", "mono_A_viol", "mono_E_viol",
            "mono_A_mag", "mono_E_mag", "smooth_penalty", "total_score"
        ])
        empty_df.to_csv(out_csv_path, index=False, encoding="utf-8")

        with open(out_summary_path, "w", encoding="utf-8") as f:
            f.write("=== Feature Gradient Search Summary ===\n\n")
            f.write(f"Run timestamp: {run_timestamp}\n")
            f.write("No feature gradients were found under the current settings.\n")

        print("No feature gradients found under the current settings.")
        print(f"Wrote empty CSV: {out_csv_path}")
        print(f"Wrote summary:   {out_summary_path}")
        return

    out_df = pd.DataFrame(all_records)

    if SEARCH_MODE == "strict":
        out_df = out_df.sort_values(
            by=["min_adj", "adj_sum"],
            ascending=[False, False]
        )
    else:
        out_df = out_df.sort_values(
            by=["total_score", "min_adj", "adj_sum"],
            ascending=[False, False, False]
        )

    out_df = out_df.head(TOP_RESULTS_TOTAL).reset_index(drop=True)
    out_df.to_csv(out_csv_path, index=False, encoding="utf-8")

    with open(out_summary_path, "w", encoding="utf-8") as f:
        f.write("=== Feature Gradient Search Summary ===\n\n")
        f.write(f"Run timestamp: {run_timestamp}\n\n")

        f.write("Inputs\n")
        f.write("------\n")
        f.write(f"Feature zero-overlap CSV: {ZERO_FEATURE_OVERLAP_CSV}\n")
        f.write(f"Incidence matrix: {INCIDENCE_PATH}\n\n")

        f.write("Filtering\n")
        f.write("---------\n")
        f.write(f"MIN_FEATURE_FREQ: {MIN_FEATURE_FREQ}\n\n")

        f.write("Endpoint settings\n")
        f.write("-----------------\n")
        f.write(f"ENDPOINT_MODE: {ENDPOINT_MODE}\n")
        if ENDPOINT_MODE == "significant":
            f.write(f"SIGNIFICANCE_COLUMN: {SIGNIFICANCE_COLUMN}\n")
        if ENDPOINT_MODE == "specific":
            f.write(f"SPECIFIC_FEATURE_A: {SPECIFIC_FEATURE_A}\n")
            f.write(f"SPECIFIC_FEATURE_E: {SPECIFIC_FEATURE_E}\n")
        f.write(f"Endpoint pairs searched: {len(endpoint_pairs)}\n\n")

        f.write("Chain settings\n")
        f.write("--------------\n")
        f.write(f"CHAIN_LENGTH_MODE: {CHAIN_LENGTH_MODE}\n")
        if CHAIN_LENGTH_MODE == "fixed":
            f.write(f"CHAIN_LENGTH: {CHAIN_LENGTH}\n")
        else:
            f.write(f"MIN_CHAIN_LENGTH: {MIN_CHAIN_LENGTH}\n")
            f.write(f"MAX_CHAIN_LENGTH: {MAX_CHAIN_LENGTH}\n")
        f.write(f"SEARCH_MODE: {SEARCH_MODE}\n")
        f.write(f"MIN_ADJ_JACCARD: {MIN_ADJ_JACCARD}\n")
        f.write(f"MIN_ADJ_COOCC: {MIN_ADJ_COOCC}\n")
        f.write(f"BEAM_WIDTH: {BEAM_WIDTH}\n")
        f.write(f"TOP_RESULTS_PER_ENDPOINT: {TOP_RESULTS_PER_ENDPOINT}\n")
        f.write(f"TOP_RESULTS_TOTAL: {TOP_RESULTS_TOTAL}\n\n")

        f.write("Search results\n")
        f.write("--------------\n")
        f.write(f"Endpoint pairs with ≥1 retained chain: {endpoint_with_results}\n")
        f.write(f"Total chains retained before global truncation: {len(all_records)}\n")
        f.write(f"Rows written: {len(out_df)}\n")
        f.write(f"Candidates discarded by adjacency filter: {discard_adj}\n")
        if SEARCH_MODE == "strict":
            f.write(f"Candidates discarded by strict gradient rules: {discard_strict}\n")
        f.write("\n")

        f.write("Interpretation\n")
        f.write("--------------\n")
        f.write("A feature gradient is a chain of features linking two endpoint features that\n")
        f.write("never co-occur directly. Strict mode returns only chains satisfying strong\n")
        f.write("gradient constraints. Ranked mode returns plausible gradients scored by\n")
        f.write("adjacency strength, monotonicity quality, and positional smoothness.\n\n")

        f.write("Output files\n")
        f.write("------------\n")
        f.write(f"{OUT_CSV}\n")
        f.write(f"{OUT_SUMMARY}\n")

    print("[✓] Feature gradient search complete.")
    print(f"    Endpoint mode:      {ENDPOINT_MODE}")
    print(f"    Search mode:        {SEARCH_MODE}")
    print(f"    Endpoint pairs:     {len(endpoint_pairs)}")
    print(f"    Pairs with results: {endpoint_with_results}")
    print(f"    Rows written:       {len(out_df)}")
    print(f"    Output CSV:         {out_csv_path}")
    print(f"    Summary:            {out_summary_path}")


if __name__ == "__main__":
    main()