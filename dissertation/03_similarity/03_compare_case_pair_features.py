#!/usr/bin/env python3
"""
03_compare_case_pair_features.py

Given a binary incidence matrix (cases × features/tropes), compare two cases and output:

- Features unique to Case A
- Features shared by A and B
- Features unique to Case B

Outputs:
1) Console summary
2) A 3-column CSV (A_only | shared | B_only)
3) Optional Markdown report (nice for GitHub / notes)

Input formats supported: .xlsx, .csv
Assumes presence marked by PRESENCE_TOKEN (default "X") and absence blank.

Typical use:
- Use on a demo dataset (e.g., 7-book sheet) or any incidence matrix dataset.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG (edit per dataset)
# ──────────────────────────────────────────────────────────────────────────────

INPUT_PATH = Path("first_7_books.xlsx")   # .xlsx or .csv
SHEET_NAME = 0                           # used only for .xlsx

# Where the case name/ID lives:
CASE_ID_COLUMN = "Source Title"          # set to None to use the row index instead

# If your table has metadata columns (Title/Author/Year/Publisher, etc.),
# features start after the first N_METADATA_COLS columns.
# If CASE_ID_COLUMN is used and is among the metadata columns, that's fine.
N_METADATA_COLS = 4

PRESENCE_TOKEN = "X"

# Optional: keep only features that appear in at least this many cases overall (e.g., 2)
MIN_FEATURE_FREQ = 2   # set to 1 to keep all features

# Pick the two cases to compare (must match values in CASE_ID_COLUMN or index)
CASE_A = "The Transformative Vision"
CASE_B = "Cosmic Trigger"

# Output files
OUTPUT_DIR = Path(".")
OUT_CSV = "case_pair_comparison.csv"
OUT_MD = "case_pair_comparison.md"       # set to None to skip Markdown output
# ──────────────────────────────────────────────────────────────────────────────


def read_table(path: Path, sheet_name=0) -> pd.DataFrame:
    """Read .xlsx or .csv as strings; keep blanks literal (not NaN)."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suf = path.suffix.lower()
    if suf in [".xlsx", ".xls"]:
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=str, keep_default_na=False)
    elif suf == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file type: {suf}. Use .xlsx/.xls or .csv")

    df.columns = df.columns.map(str)
    return df


def get_feature_columns(df: pd.DataFrame, n_metadata_cols: int) -> List[str]:
    if n_metadata_cols < 0 or n_metadata_cols >= df.shape[1]:
        raise ValueError(
            f"N_METADATA_COLS={n_metadata_cols} invalid for dataframe with {df.shape[1]} columns."
        )
    return list(df.columns[n_metadata_cols:])


def binarize_features(df: pd.DataFrame, feature_cols: List[str], token: str) -> pd.DataFrame:
    """Return 0/1 incidence matrix for the feature columns."""
    inc = df[feature_cols].eq(token).astype(int)
    # drop all-zero columns
    inc = inc.loc[:, inc.sum(axis=0) > 0]
    return inc


def pad_columns(a: List[str], b: List[str], c: List[str]) -> pd.DataFrame:
    """Make a 3-column table with blank padding so lengths align."""
    max_len = max(len(a), len(b), len(c), 1)
    def pad(lst: List[str]) -> List[str]:
        return lst + [""] * (max_len - len(lst))
    return pd.DataFrame({
        "A_only": pad(a),
        "Shared": pad(b),
        "B_only": pad(c),
    })


def write_markdown_report(
    md_path: Path,
    case_a: str,
    case_b: str,
    n_features_total: int,
    n_features_used: int,
    a_only: List[str],
    shared: List[str],
    b_only: List[str],
) -> None:
    md_lines = []
    md_lines.append(f"# Case Pair Feature Comparison\n")
    md_lines.append(f"**Case A:** {case_a}\n")
    md_lines.append(f"**Case B:** {case_b}\n")
    md_lines.append(f"- Features in dataset (after dropping all-zero): **{n_features_total:,}**\n")
    md_lines.append(f"- Features considered (after MIN_FEATURE_FREQ filter): **{n_features_used:,}**\n")
    md_lines.append(f"- A-only: **{len(a_only):,}**  | Shared: **{len(shared):,}**  | B-only: **{len(b_only):,}**\n")

    md_lines.append("\n---\n")
    md_lines.append("## Results\n")
    md_lines.append("| A-only | Shared | B-only |\n")
    md_lines.append("|---|---|---|\n")

    table = pad_columns(a_only, shared, b_only)
    for _, row in table.iterrows():
        md_lines.append(f"| {row['A_only']} | {row['Shared']} | {row['B_only']} |\n")

    md_path.write_text("".join(md_lines), encoding="utf-8")


def main() -> None:
    df = read_table(INPUT_PATH, sheet_name=SHEET_NAME)

    # Determine case ids (index vs column)
    if CASE_ID_COLUMN is None:
        df = df.copy()
        df.index = df.index.map(str)
        case_ids = df.index
    else:
        if CASE_ID_COLUMN not in df.columns:
            raise ValueError(f"CASE_ID_COLUMN '{CASE_ID_COLUMN}' not found in columns.")
        case_ids = df[CASE_ID_COLUMN].map(str)

    feature_cols = get_feature_columns(df, N_METADATA_COLS)
    if not feature_cols:
        raise ValueError("No feature columns found. Check N_METADATA_COLS.")

    inc = binarize_features(df, feature_cols, PRESENCE_TOKEN)
    n_features_total = inc.shape[1]

    # Apply global feature frequency filter (optional)
    feature_freq = inc.sum(axis=0)
    inc_f = inc.loc[:, feature_freq >= MIN_FEATURE_FREQ]
    n_features_used = inc_f.shape[1]

    # Select the two rows
    if CASE_ID_COLUMN is None:
        if CASE_A not in df.index or CASE_B not in df.index:
            raise ValueError("One or both CASE_A/CASE_B not found in the index.")
        rowA = inc_f.loc[CASE_A]
        rowB = inc_f.loc[CASE_B]
    else:
        maskA = df[CASE_ID_COLUMN].map(str) == str(CASE_A)
        maskB = df[CASE_ID_COLUMN].map(str) == str(CASE_B)
        if maskA.sum() != 1 or maskB.sum() != 1:
            raise ValueError(
                "CASE_A/CASE_B must each match exactly one row. "
                "If duplicates exist, use a unique ID column."
            )
        rowA = inc_f.loc[maskA].squeeze()
        rowB = inc_f.loc[maskB].squeeze()

    setA = {feat for feat, v in rowA.items() if int(v) == 1}
    setB = {feat for feat, v in rowB.items() if int(v) == 1}

    shared = sorted(setA & setB)
    a_only = sorted(setA - setB)
    b_only = sorted(setB - setA)

    # Console output (quick glance)
    print(f"[✓] Compared cases:")
    print(f"    A: {CASE_A}")
    print(f"    B: {CASE_B}")
    print(f"    Features: {n_features_total:,} (nonzero) | {n_features_used:,} (after MIN_FEATURE_FREQ ≥ {MIN_FEATURE_FREQ})")
    print(f"    A-only: {len(a_only):,} | Shared: {len(shared):,} | B-only: {len(b_only):,}\n")

    # Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv_path = OUTPUT_DIR / OUT_CSV
    table = pad_columns(a_only, shared, b_only)
    table.to_csv(out_csv_path, index=False, encoding="utf-8")
    print(f"[✓] Wrote 3-column comparison CSV: {out_csv_path}")

    # Optional Markdown
    if OUT_MD:
        out_md_path = OUTPUT_DIR / OUT_MD
        write_markdown_report(
            out_md_path,
            case_a=CASE_A,
            case_b=CASE_B,
            n_features_total=n_features_total,
            n_features_used=n_features_used,
            a_only=a_only,
            shared=shared,
            b_only=b_only,
        )
        print(f"[✓] Wrote Markdown report: {out_md_path}")


if __name__ == "__main__":
    main()