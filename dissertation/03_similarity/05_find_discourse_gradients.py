#!/usr/bin/env python3
"""
05_find_discourse_gradients.py

Find discourse gradients between zero-overlap endpoint pairs using an existing
zero-overlap table, Jaccard similarity matrix, and original incidence matrix.

A discourse gradient is a chain of cases:

    A -> ... -> E

such that:
- A and E are zero-overlap endpoints
- adjacent pairs share meaningful overlap
- the chain moves gradually from A's repertoire toward E's repertoire

This script supports:

Endpoint selection modes
------------------------
1) all
   Use all zero-overlap pairs from the zero-overlap CSV

2) significant
   Use only zero-overlap pairs passing a chosen significance column
   (e.g. sig_0.05)

3) specific
   Use one user-specified zero-overlap pair only

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
   - optional minimum adjacent intersection count
   - strict monotone decrease in similarity to A
   - strict monotone increase in similarity to E
   - neighborhood dominance

2) ranked
   Requires only:
   - minimum adjacent Jaccard
   - optional minimum adjacent intersection count

   Then scores candidate chains by:
   - adjacency strength
   - monotonicity quality
   - positional smoothness

Outputs
-------
1) discourse_gradients.csv
   One row per retained chain, with endpoint pair, chain members, adjacent
   similarities/intersections, and score fields.

2) analysis_summary.txt
   Human-readable record of inputs, settings, and results.
"""

from __future__ import annotations

from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

# Inputs
ZERO_OVERLAP_CSV = Path("zero_overlap_pairs_with_significance.csv")
JACCARD_CSV = Path("jaccard_similarity_matrix.csv")
INCIDENCE_PATH = Path("input_incidence_matrix.xlsx")   # .xlsx or .csv
SHEET_NAME = 0

# Incidence matrix structure
CASE_ID_COLUMN = "Source Title"
N_METADATA_COLS = 4
PRESENCE_TOKEN = "X"

# Endpoint selection
ENDPOINT_MODE = "significant"     # "all", "significant", or "specific"
SIGNIFICANCE_COLUMN = "sig_0.05"  # used only if ENDPOINT_MODE = "significant"

# Used only if ENDPOINT_MODE = "specific"
SPECIFIC_CASE_A = ""
SPECIFIC_CASE_E = ""

# Chain length
CHAIN_LENGTH_MODE = "fixed"       # "fixed" or "range"
CHAIN_LENGTH = 5                  # used only if CHAIN_LENGTH_MODE = "fixed"
MIN_CHAIN_LENGTH = 4              # used only if CHAIN_LENGTH_MODE = "range"
MAX_CHAIN_LENGTH = 6              # used only if CHAIN_LENGTH_MODE = "range"

# Search mode
SEARCH_MODE = "ranked"            # "strict" or "ranked"

# Adjacency strength requirements
MIN_ADJ = 0.20                    # minimum Jaccard for each adjacent pair
MIN_INTERSECTION = 0              # set > 0 to require minimum shared features per adjacent pair

# Beam search / output
BEAM_WIDTH = 20                   # near-ideal candidates kept per interior target position
TOP_RESULTS_PER_ENDPOINT = 10     # max chains retained per endpoint pair
TOP_RESULTS_TOTAL = 100           # total rows written

# Numerical tolerance
EPS = 1e-9

# Output
OUTPUT_DIR = Path(".")
OUT_CSV = "discourse_gradients.csv"
OUT_SUMMARY = "analysis_summary.txt"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS: reading and cleaning
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
# HELPERS: chain evaluation
# ──────────────────────────────────────────────────────────────────────────────

def t_coord_all(case_order: List[str], jmat_df: pd.DataFrame, a: str, e: str) -> pd.Series:
    """
    Projection coordinate:
        t(x) = (J(x,A) - J(x,E)) / (J(x,A) + J(x,E))
    """
    sA = jmat_df.loc[case_order, a]
    sE = jmat_df.loc[case_order, e]
    return (sA - sE) / (sA + sE + 1e-12)


def adjacency_passes(chain: List[str], jmat_df: pd.DataFrame, imat_df: pd.DataFrame) -> bool:
    """Hard adjacency requirements used in both strict and ranked modes."""
    for u, v in zip(chain[:-1], chain[1:]):
        if float(jmat_df.loc[u, v]) + EPS < MIN_ADJ:
            return False
        if MIN_INTERSECTION > 0 and int(imat_df.loc[u, v]) < MIN_INTERSECTION:
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

    # strict monotone to A (descending)
    if not all(sA[k] > sA[k + 1] + EPS for k in range(len(chain) - 1)):
        return False

    # strict monotone to E (ascending)
    if not all(sE[k] + EPS < sE[k + 1] for k in range(len(chain) - 1)):
        return False

    # neighborhood dominance
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

    # Adjacent similarities
    adj_js = [float(jmat_df.loc[u, v]) for u, v in zip(chain[:-1], chain[1:])]
    min_adj = min(adj_js)
    adj_sum = sum(adj_js)

    # Monotonicity penalties
    sA = [float(jmat_df.loc[x, A]) for x in chain]
    sE = [float(jmat_df.loc[x, E]) for x in chain]

    mono_A_viol = 0
    mono_E_viol = 0
    mono_A_mag = 0.0
    mono_E_mag = 0.0

    for k in range(m - 1):
        # Want sA[k] > sA[k+1]
        if not (sA[k] > sA[k + 1] + EPS):
            mono_A_viol += 1
            mono_A_mag += max(0.0, sA[k + 1] - sA[k])

        # Want sE[k] < sE[k+1]
        if not (sE[k] + EPS < sE[k + 1]):
            mono_E_viol += 1
            mono_E_mag += max(0.0, sE[k] - sE[k + 1])

    # Positional smoothness: compare interior nodes to ideal t targets
    # Interior target positions evenly spaced between +1 and -1
    # Example m=5 => [0.5, 0.0, -0.5]
    if m <= 2:
        smooth_penalty = 0.0
    else:
        targets = np.linspace(1, -1, m)[1:-1]
        actuals = np.array([float(t_map.loc[x]) for x in chain[1:-1]])
        smooth_penalty = float(np.abs(actuals - targets).sum())

    # Total score: reward strong adjacency, penalize violations and poor smoothness
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
    imat_df: pd.DataFrame,
    t_map: pd.Series,
) -> Dict[str, object]:
    """Create one output row for a chain."""
    record: Dict[str, object] = {
        "endpoint_mode": endpoint_mode,
        "search_mode": search_mode,
        "significance_column": sig_col if endpoint_mode == "significant" else "",
        "case_A": chain[0],
        "case_E": chain[-1],
        "chain_length": len(chain),
        "chain": " | ".join(chain),
    }

    # Case columns
    for idx, case in enumerate(chain, start=1):
        record[f"case_{idx}"] = case

    # Adjacent Jaccard / intersections
    adj_pairs = list(zip(chain[:-1], chain[1:]))
    for idx, (u, v) in enumerate(adj_pairs, start=1):
        record[f"adj_{idx}_pair"] = f"{u} -> {v}"
        record[f"adj_{idx}_jaccard"] = round(float(jmat_df.loc[u, v]), 6)
        record[f"adj_{idx}_intersection"] = int(imat_df.loc[u, v])

    # Similarity sequences to endpoints
    sA = [round(float(jmat_df.loc[x, chain[0]]), 6) for x in chain]
    sE = [round(float(jmat_df.loc[x, chain[-1]]), 6) for x in chain]
    record["sim_to_A_seq"] = str(sA)
    record["sim_to_E_seq"] = str(sE)

    # t-coordinates for interior nodes
    if len(chain) > 2:
        record["interior_t_seq"] = str([round(float(t_map.loc[x]), 6) for x in chain[1:-1]])
    else:
        record["interior_t_seq"] = "[]"

    # Strict pass (useful to report even in strict mode)
    record["strict_pass"] = strict_gradient_ok(chain, jmat_df)

    # Ranked score fields
    score_fields = ranked_chain_score(chain, jmat_df, t_map)
    record.update(score_fields)

    return record


def build_intersection_matrix(case_order: List[str], X: np.ndarray) -> pd.DataFrame:
    """Case × case raw intersection counts."""
    n = len(case_order)
    mat = np.zeros((n, n), dtype=int)
    for i in range(n):
        ai = X[i]
        for j in range(i, n):
            inter = int(np.bitwise_and(ai, X[j]).sum())
            mat[i, j] = inter
            mat[j, i] = inter
    return pd.DataFrame(mat, index=case_order, columns=case_order)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Read zero-overlap table ──────────────────────────────────────────────
    if not ZERO_OVERLAP_CSV.exists():
        raise FileNotFoundError(f"Zero-overlap CSV not found: {ZERO_OVERLAP_CSV}")

    zero_df = pd.read_csv(ZERO_OVERLAP_CSV)

    required_zero_cols = {"case_A", "case_B"}
    if not required_zero_cols.issubset(zero_df.columns):
        raise ValueError(
            f"{ZERO_OVERLAP_CSV} must contain columns: {sorted(required_zero_cols)}"
        )

    # Normalize pair order
    zero_df[["case_A", "case_B"]] = zero_df[["case_A", "case_B"]].astype(str)

    # ─── Read Jaccard matrix ─────────────────────────────────────────────────
    if not JACCARD_CSV.exists():
        raise FileNotFoundError(f"Jaccard CSV not found: {JACCARD_CSV}")

    jmat_df = pd.read_csv(JACCARD_CSV, index_col=0)
    jmat_df.index = jmat_df.index.map(str)
    jmat_df.columns = jmat_df.columns.map(str)

    if list(jmat_df.index) != list(jmat_df.columns):
        raise ValueError("JACCARD_CSV must be a square matrix with matching row/column labels.")

    case_order = list(jmat_df.index)

    # ─── Read incidence matrix for intersections ─────────────────────────────
    inc_raw = read_table(INCIDENCE_PATH, sheet_name=SHEET_NAME)
    if CASE_ID_COLUMN not in inc_raw.columns:
        raise ValueError(f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in {INCIDENCE_PATH}")

    producer_index = inc_raw.columns.get_loc(CASE_ID_COLUMN)
    if producer_index >= N_METADATA_COLS:
        raise ValueError(
            f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' is outside the first {N_METADATA_COLS} columns.\n"
            "This script assumes that all metadata columns appear to the LEFT of the feature columns."
        )

    feature_cols = get_feature_columns(inc_raw, N_METADATA_COLS)
    inc = pd.concat([inc_raw[[CASE_ID_COLUMN]], inc_raw[feature_cols]], axis=1).copy()
    bin_features = binarize_presence(inc, feature_cols, PRESENCE_TOKEN)
    bin_df = pd.concat([inc[[CASE_ID_COLUMN]].copy(), bin_features], axis=1)
    bin_df[CASE_ID_COLUMN] = bin_df[CASE_ID_COLUMN].astype(str)

    # Keep only cases that appear in the Jaccard matrix
    bin_df = bin_df[bin_df[CASE_ID_COLUMN].isin(case_order)].copy()

    # Reindex to match Jaccard order
    bin_df = bin_df.set_index(CASE_ID_COLUMN).reindex(case_order)
    if bin_df.isna().any().any():
        missing_cases = bin_df.index[bin_df.isna().any(axis=1)].tolist()
        raise ValueError(
            "Some cases in the Jaccard matrix are missing from the incidence matrix after alignment: "
            f"{missing_cases[:10]}"
        )

    X = bin_df.values.astype(np.uint8)
    imat_df = build_intersection_matrix(case_order, X)

    # ─── Endpoint selection ───────────────────────────────────────────────────
    if ENDPOINT_MODE not in {"all", "significant", "specific"}:
        raise ValueError("ENDPOINT_MODE must be 'all', 'significant', or 'specific'.")

    if ENDPOINT_MODE == "all":
        endpoint_df = zero_df.copy()

    elif ENDPOINT_MODE == "significant":
        if SIGNIFICANCE_COLUMN not in zero_df.columns:
            raise ValueError(
                f"SIGNIFICANCE_COLUMN '{SIGNIFICANCE_COLUMN}' not found in {ZERO_OVERLAP_CSV}"
            )
        endpoint_df = zero_df[zero_df[SIGNIFICANCE_COLUMN].astype(bool)].copy()

    else:  # specific
        if not SPECIFIC_CASE_A or not SPECIFIC_CASE_E:
            raise ValueError(
                "For ENDPOINT_MODE='specific', set both SPECIFIC_CASE_A and SPECIFIC_CASE_E."
            )

        a, e = normalize_pair(str(SPECIFIC_CASE_A), str(SPECIFIC_CASE_E))
        pair_mask = (
            zero_df.apply(lambda r: normalize_pair(str(r["case_A"]), str(r["case_B"])), axis=1) == (a, e)
        )
        endpoint_df = zero_df[pair_mask].copy()

        if endpoint_df.empty:
            raise ValueError(
                f"The specified pair ({SPECIFIC_CASE_A}, {SPECIFIC_CASE_E}) was not found "
                "in the zero-overlap table."
            )

    # Normalize endpoint pairs, deduplicate
    endpoint_pairs = []
    seen_pairs = set()

    for _, row in endpoint_df.iterrows():
        a, e = normalize_pair(str(row["case_A"]), str(row["case_B"]))
        if a not in case_order or e not in case_order:
            continue
        # Double-check zero overlap
        if float(jmat_df.loc[a, e]) > EPS:
            continue
        if (a, e) not in seen_pairs:
            seen_pairs.add((a, e))
            endpoint_pairs.append((a, e))

    if not endpoint_pairs:
        raise ValueError("No valid zero-overlap endpoint pairs remained after filtering.")

    # ─── Chain lengths ────────────────────────────────────────────────────────
    if CHAIN_LENGTH_MODE not in {"fixed", "range"}:
        raise ValueError("CHAIN_LENGTH_MODE must be 'fixed' or 'range'.")

    if CHAIN_LENGTH_MODE == "fixed":
        chain_lengths = [CHAIN_LENGTH]
    else:
        chain_lengths = list(range(MIN_CHAIN_LENGTH, MAX_CHAIN_LENGTH + 1))

    if min(chain_lengths) < 3:
        raise ValueError("Minimum chain length must be at least 3.")
    if max(chain_lengths) > len(case_order):
        raise ValueError("Chain length exceeds number of available cases.")

    # ─── Search ───────────────────────────────────────────────────────────────
    all_records: List[Dict[str, object]] = []
    discard_adj = 0
    discard_strict = 0
    endpoint_with_results = 0

    for a, e in endpoint_pairs:
        t_map = t_coord_all(case_order, jmat_df, a, e)
        pool_idx = [k for k, c in enumerate(case_order) if c not in (a, e)]

        endpoint_records: List[Dict[str, object]] = []

        for chain_len in chain_lengths:
            n_interior = chain_len - 2
            if n_interior <= 0:
                continue

            # Interior target positions between +1 and -1
            targets = np.linspace(1, -1, chain_len)[1:-1]

            # For each interior position, build a beam of nearby cases
            beams: List[List[str]] = []
            for tgt in targets:
                ranked_cases = sorted(
                    [case_order[k] for k in pool_idx],
                    key=lambda c: (
                        abs(float(t_map.loc[c]) - tgt),
                        -float(jmat_df.loc[c, a]),
                        float(jmat_df.loc[c, e]),
                    )
                )
                beams.append(ranked_cases[:BEAM_WIDTH])

            # Cartesian search over beams
            # We use product-like nested logic with combinations by recursion
            def recurse_build(pos: int, partial: List[str]) -> None:
                nonlocal discard_adj, discard_strict, endpoint_records

                if pos == len(beams):
                    chain = [a] + partial + [e]

                    # Distinctness
                    if len(set(chain)) != len(chain):
                        return

                    # Hard adjacency filter
                    if not adjacency_passes(chain, jmat_df, imat_df):
                        discard_adj += 1
                        return

                    # Search mode handling
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
                        imat_df=imat_df,
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

            # Ranking within endpoint
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

    # ─── Final output ─────────────────────────────────────────────────────────
    out_csv_path = OUTPUT_DIR / OUT_CSV
    out_summary_path = OUTPUT_DIR / OUT_SUMMARY

    if not all_records:
        empty_df = pd.DataFrame(columns=[
            "endpoint_mode", "search_mode", "significance_column",
            "case_A", "case_E", "chain_length", "chain", "strict_pass",
            "min_adj", "adj_sum", "mono_A_viol", "mono_E_viol",
            "mono_A_mag", "mono_E_mag", "smooth_penalty", "total_score"
        ])
        empty_df.to_csv(out_csv_path, index=False, encoding="utf-8")

        with open(out_summary_path, "w", encoding="utf-8") as f:
            f.write("=== Discourse Gradient Search Summary ===\n\n")
            f.write(f"Run timestamp: {run_timestamp}\n")
            f.write("No discourse gradients were found under the current settings.\n\n")
            f.write("Inputs\n")
            f.write("------\n")
            f.write(f"Zero-overlap CSV: {ZERO_OVERLAP_CSV}\n")
            f.write(f"Jaccard CSV: {JACCARD_CSV}\n")
            f.write(f"Incidence matrix: {INCIDENCE_PATH}\n")

        print("No discourse gradients found under the current settings.")
        print(f"Wrote empty CSV: {out_csv_path}")
        print(f"Wrote summary:   {out_summary_path}")
        return

    out_df = pd.DataFrame(all_records)

    # Global ranking
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

    # Summary
    with open(out_summary_path, "w", encoding="utf-8") as f:
        f.write("=== Discourse Gradient Search Summary ===\n\n")
        f.write(f"Run timestamp: {run_timestamp}\n\n")

        f.write("Inputs\n")
        f.write("------\n")
        f.write(f"Zero-overlap CSV: {ZERO_OVERLAP_CSV}\n")
        f.write(f"Jaccard CSV: {JACCARD_CSV}\n")
        f.write(f"Incidence matrix: {INCIDENCE_PATH}\n\n")

        f.write("Endpoint settings\n")
        f.write("-----------------\n")
        f.write(f"ENDPOINT_MODE: {ENDPOINT_MODE}\n")
        if ENDPOINT_MODE == "significant":
            f.write(f"SIGNIFICANCE_COLUMN: {SIGNIFICANCE_COLUMN}\n")
        if ENDPOINT_MODE == "specific":
            f.write(f"SPECIFIC_CASE_A: {SPECIFIC_CASE_A}\n")
            f.write(f"SPECIFIC_CASE_E: {SPECIFIC_CASE_E}\n")
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
        f.write(f"MIN_ADJ: {MIN_ADJ}\n")
        f.write(f"MIN_INTERSECTION: {MIN_INTERSECTION}\n")
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
        f.write("Strict mode returns only chains that satisfy strong gradient constraints,\n")
        f.write("including strict monotonicity and neighborhood dominance.\n")
        f.write("Ranked mode returns plausible gradients scored by adjacency strength,\n")
        f.write("monotonicity quality, and positional smoothness, without requiring\n")
        f.write("neighborhood dominance.\n\n")

        f.write("Output files\n")
        f.write("------------\n")
        f.write(f"{OUT_CSV}\n")
        f.write(f"{OUT_SUMMARY}\n")

    print("[✓] Discourse gradient search complete.")
    print(f"    Endpoint mode:      {ENDPOINT_MODE}")
    print(f"    Search mode:        {SEARCH_MODE}")
    print(f"    Endpoint pairs:     {len(endpoint_pairs)}")
    print(f"    Pairs with results: {endpoint_with_results}")
    print(f"    Rows written:       {len(out_df)}")
    print(f"    Output CSV:         {out_csv_path}")
    print(f"    Summary:            {out_summary_path}")


if __name__ == "__main__":
    main()