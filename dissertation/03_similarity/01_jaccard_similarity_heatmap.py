#!/usr/bin/env python3
"""
01_jaccard_similarity_heatmap.py

Compute a case×case Jaccard similarity matrix from a binary incidence matrix
(case × feature/trope) stored in .xlsx or .csv, optionally filter to “shared”
features (min feature frequency), and export:

1) Jaccard similarity matrix as CSV
2) Heatmap as PNG (optional)

Designed for datasets like “books × tropes” spreadsheets where presence is marked
with a token (default: "X") and absence is blank.

Typical use (after editing CONFIG below):
    python jaccard_similarity_heatmap.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import jaccard_score


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG (edit these per dataset)
# ──────────────────────────────────────────────────────────────────────────────

# Input file (.xlsx or .csv)
INPUT_PATH = Path("first_7_books.xlsx")

# Column containing case names (book titles, song IDs, etc.).
# If None, the script will prefer "Source Title" if present, otherwise "Title",
# otherwise it will fall back to row numbers.
TITLE_COL: Optional[str] = None

# If your file has metadata columns before feature/trope columns, specify how many.
# For your 7-book sheet, tropes begin at column E → N_METADATA_COLS = 4.
N_METADATA_COLS = 4

# Presence token in the spreadsheet
PRESENCE_TOKEN = "X"

# Keep only features/tropes that appear in at least this many cases (default: 2)
MIN_FEATURE_FREQ = 2

# Output directory (defaults to where you run the script from)
OUTPUT_DIR = Path(".")

# Output filenames
OUT_CSV = "jaccard_similarity_thr2.csv"
OUT_PNG = "jaccard_similarity_thr2.png"

# Plot options
MAKE_PLOT = True
FIGSIZE = (12, 10)
DPI = 300
ANNOTATE_CELLS = True
ANNOT_FORMAT = ".2f"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _read_table(path: Path) -> pd.DataFrame:
    """Read .xlsx or .csv as strings; keep blanks literal (not NaN)."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    elif suffix == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Use .xlsx/.xls or .csv")

    # Ensure column labels are strings (helps if you have numeric trope names)
    df.columns = df.columns.map(str)
    return df


def _choose_title_col(df: pd.DataFrame, preferred: Optional[str]) -> Optional[str]:
    """Pick a reasonable title/case-id column, if available."""
    if preferred is not None:
        if preferred not in df.columns:
            raise ValueError(
                f"TITLE_COL was set to {preferred!r}, but that column was not found.\n"
                f"Available columns include: {list(df.columns)[:10]} ..."
            )
        return preferred

    # Common patterns in your datasets
    if "Source Title" in df.columns:
        return "Source Title"
    if "Title" in df.columns:
        return "Title"

    return None


def _extract_case_names(df: pd.DataFrame, title_col: Optional[str]) -> list[str]:
    """Return a list of case names aligned to dataframe rows."""
    if title_col is None:
        return [f"row_{i+1}" for i in range(len(df))]
    names = df[title_col].astype(str).tolist()

    # If duplicates exist, disambiguate to keep labels unique (Gephi & matrices prefer unique ids)
    seen = {}
    out = []
    for n in names:
        if n not in seen:
            seen[n] = 1
            out.append(n)
        else:
            seen[n] += 1
            out.append(f"{n} ({seen[n]})")
    return out


def _build_incidence(df: pd.DataFrame, n_metadata_cols: int, token: str) -> Tuple[pd.DataFrame, list[str]]:
    """
    Build a binary incidence matrix (cases × features) from df.
    Assumes features begin after the first n_metadata_cols columns.
    """
    if n_metadata_cols < 0 or n_metadata_cols >= df.shape[1]:
        raise ValueError(
            f"N_METADATA_COLS={n_metadata_cols} is invalid for a table with {df.shape[1]} columns."
        )

    feature_cols = list(df.columns[n_metadata_cols:])
    if not feature_cols:
        raise ValueError("No feature columns found. Check N_METADATA_COLS and your input file.")

    incidence = df[feature_cols].eq(token).astype(int)
    return incidence, feature_cols


def _filter_features_by_freq(incidence: pd.DataFrame, min_freq: int) -> pd.DataFrame:
    """Keep features that appear in ≥ min_freq cases."""
    if min_freq <= 1:
        return incidence
    freq = incidence.sum(axis=0)
    return incidence.loc[:, freq >= min_freq]


def _compute_jaccard_matrix(incidence: pd.DataFrame, case_names: list[str]) -> pd.DataFrame:
    """
    Compute a symmetric case×case Jaccard matrix.
    Computes only the upper triangle and mirrors to avoid redundant work.
    """
    n_cases = incidence.shape[0]
    if n_cases != len(case_names):
        raise ValueError("case_names length does not match number of rows in incidence matrix.")

    mat = np.zeros((n_cases, n_cases), dtype=float)

    # Diagonal is always 1.0 (each case identical to itself) *unless* a row is all zeros.
    # sklearn's jaccard_score will return 0.0 if both are all zeros (undefined union); we handle explicitly.
    row_sums = incidence.sum(axis=1).to_numpy()
    all_zero = (row_sums == 0)

    # Preconvert to numpy for speed
    X = incidence.to_numpy(dtype=int)

    for i in range(n_cases):
        # self-sim
        mat[i, i] = 0.0 if all_zero[i] else 1.0

        for j in range(i + 1, n_cases):
            # If both are all-zero, define similarity as 0.0 (no shared presences, undefined union)
            if all_zero[i] and all_zero[j]:
                sim = 0.0
            else:
                sim = float(jaccard_score(X[i], X[j]))
            mat[i, j] = sim
            mat[j, i] = sim

    return pd.DataFrame(mat, index=case_names, columns=case_names)


def _plot_heatmap(jaccard_df: pd.DataFrame, out_png: Path) -> None:
    """Plot and save a heatmap. Uses seaborn if available; falls back to matplotlib."""
    import matplotlib.pyplot as plt

    # Prefer seaborn if installed (nicer heatmap + annotations)
    try:
        import seaborn as sns  # type: ignore
        use_seaborn = True
    except Exception:
        sns = None
        use_seaborn = False

    fig, ax = plt.subplots(figsize=FIGSIZE, constrained_layout=True)

    data = jaccard_df.to_numpy(dtype=float)

    if use_seaborn:
        sns.heatmap(
            jaccard_df.astype(float),
            annot=ANNOTATE_CELLS,
            fmt=ANNOT_FORMAT,
            vmin=0,
            vmax=1,
            ax=ax,
        )
    else:
        im = ax.imshow(data, vmin=0, vmax=1)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        if ANNOTATE_CELLS:
            for (i, j), val in np.ndenumerate(data):
                ax.text(j, i, format(val, ANNOT_FORMAT), ha="center", va="center")

        ax.set_xticks(range(jaccard_df.shape[1]))
        ax.set_yticks(range(jaccard_df.shape[0]))
        ax.set_xticklabels(jaccard_df.columns.tolist())
        ax.set_yticklabels(jaccard_df.index.tolist())

    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    ax.set_title(f"Jaccard Similarity (features with freq ≥ {MIN_FEATURE_FREQ})")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    df = _read_table(INPUT_PATH)

    title_col = _choose_title_col(df, TITLE_COL)
    case_names = _extract_case_names(df, title_col)

    incidence, feature_cols = _build_incidence(df, N_METADATA_COLS, PRESENCE_TOKEN)
    n_features_total = len(feature_cols)

    filtered = _filter_features_by_freq(incidence, MIN_FEATURE_FREQ)
    n_features_kept = filtered.shape[1]

    jaccard_df = _compute_jaccard_matrix(filtered, case_names)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUTPUT_DIR / OUT_CSV
    out_png = OUTPUT_DIR / OUT_PNG

    jaccard_df.to_csv(out_csv, encoding="utf-8")
    if MAKE_PLOT:
        _plot_heatmap(jaccard_df, out_png)

    # Compact summary
    print("Jaccard similarity complete.")
    print(f"  Input:               {INPUT_PATH}")
    print(f"  Cases (rows):        {len(case_names):,}")
    print(f"  Features (total):    {n_features_total:,}")
    print(f"  Features kept (≥{MIN_FEATURE_FREQ}): {n_features_kept:,}")
    print(f"  Wrote matrix CSV:    {out_csv}")
    if MAKE_PLOT:
        print(f"  Wrote heatmap PNG:   {out_png}")
    else:
        print("  Heatmap:             (disabled)")


if __name__ == "__main__":
    main()