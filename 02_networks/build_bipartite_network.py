#!/usr/bin/env python3
"""
Bipartite Book–Trope Network Builder (and Pairwise Overlap CSV)

Input:
- An Excel (.xlsx/.xls) or CSV (.csv) table where:
  - Rows represent cases (e.g., books).
  - Columns include some metadata columns followed by trope columns.
  - Trope presence is marked with PRESENCE_TOKEN (default: "X"); blank means absent.

Outputs:
1) A bipartite GEXF network suitable for Gephi:
   - Nodes: books + tropes
   - Edges: book–trope incidence (unweighted)

2) A pairwise overlap CSV:
   - For every book pair, lists:
     - shared tropes
     - unshared tropes (symmetric difference)
"""

from __future__ import annotations

from pathlib import Path
from itertools import combinations
import pandas as pd
import networkx as nx


# =========================
# USER SETTINGS
# =========================

INPUT_PATH = "first_7_books.xlsx"   # .xlsx/.xls or .csv
PRESENCE_TOKEN = "X"

# If your file includes metadata columns before tropes, set how many:
N_METADATA_COLS = 4  # e.g., Title/Author/Year/Publisher

# Column containing the case label (book title). Must exist in the input.
BOOK_ID_COLUMN = "Source Title"

# Optional safeguard: drop columns by name (e.g., if someone forgot to remove a metadata column)
DROP_COLUMNS: list[str] = []

# Output names (default: based on input file name)
OUTPUT_DIR = Path(".")
BIPARTITE_GEXF_NAME = None          # e.g., "first7_bipartite.gexf" or None for auto
PAIRWISE_CSV_NAME = None            # e.g., "first7_pairwise.csv" or None for auto

# If BOOK_ID_COLUMN has duplicates, we can disambiguate by appending a suffix.
DISAMBIGUATE_DUPLICATE_BOOK_IDS = True


# =========================
# HELPERS
# =========================

def load_table(path: str) -> pd.DataFrame:
    """Load .xlsx/.xls or .csv as strings, preserving blanks."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {p.resolve()}")

    suffix = p.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(p, dtype=str, keep_default_na=False)
    elif suffix == ".csv":
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
    else:
        raise ValueError("Unsupported file type. Use .xlsx/.xls or .csv.")

    # Ensure columns are strings (helps if Excel had numeric headers)
    df.columns = df.columns.map(str)
    return df


def disambiguate_labels(labels: list[str]) -> list[str]:
    """If duplicate labels exist, append ' (2)', ' (3)' to later duplicates."""
    seen = {}
    out = []
    for lab in labels:
        count = seen.get(lab, 0) + 1
        seen[lab] = count
        out.append(lab if count == 1 else f"{lab} ({count})")
    return out


# =========================
# MAIN
# =========================

def main() -> None:
    df = load_table(INPUT_PATH)

    # Optional column drop safeguard
    if DROP_COLUMNS:
        missing = [c for c in DROP_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"DROP_COLUMNS contains columns not found in data: {missing}")
        df = df.drop(columns=DROP_COLUMNS)

    # Validate BOOK_ID_COLUMN
    if BOOK_ID_COLUMN not in df.columns:
        raise ValueError(
            f"BOOK_ID_COLUMN '{BOOK_ID_COLUMN}' not found. "
            f"Available columns include: {list(df.columns)[:10]}..."
        )

    # Determine trope columns (everything after N_METADATA_COLS)
    if N_METADATA_COLS < 0 or N_METADATA_COLS > len(df.columns):
        raise ValueError("N_METADATA_COLS is out of range for this dataset.")

    trope_cols = list(df.columns[N_METADATA_COLS:])
    if not trope_cols:
        raise ValueError(
            "No trope columns found. Check N_METADATA_COLS and your input file structure."
        )

    # Build incidence matrix for tropes only: X -> 1 else 0
    inc = df[trope_cols].eq(PRESENCE_TOKEN).astype(int)

    # Extract book labels
    books_raw = df[BOOK_ID_COLUMN].astype(str).tolist()
    if DISAMBIGUATE_DUPLICATE_BOOK_IDS:
        books = disambiguate_labels(books_raw)
    else:
        books = books_raw

    # -------------------------
    # Build bipartite graph
    # -------------------------
    B = nx.Graph()

    # Add nodes with a 'type' attribute AND a numeric bipartite partition (0/1).
    # This matches a common Gephi-friendly convention.
    for b in books:
        B.add_node(b, type="book", bipartite=0)

    for t in trope_cols:
        B.add_node(t, type="trope", bipartite=1)

    # Add edges where trope present in a given book
    # (Edges are unweighted incidence edges.)
    for book_label, row in zip(books, inc.itertuples(index=False, name=None)):
        # row is a tuple of 0/1 values aligned with trope_cols
        for trope, val in zip(trope_cols, row):
            if val:
                B.add_edge(book_label, trope)

    # Add graph-level provenance metadata (optional but helpful)
    B.graph["source_file"] = str(Path(INPUT_PATH).name)
    B.graph["presence_token"] = PRESENCE_TOKEN
    B.graph["book_id_column"] = BOOK_ID_COLUMN
    B.graph["n_metadata_cols"] = N_METADATA_COLS

    # Output filenames
    stem = Path(INPUT_PATH).stem
    gexf_name = BIPARTITE_GEXF_NAME or f"{stem}_book_trope_bipartite.gexf"
    csv_name = PAIRWISE_CSV_NAME or f"{stem}_pairwise_overlap.csv"

    gexf_path = OUTPUT_DIR / gexf_name
    csv_path = OUTPUT_DIR / csv_name

    nx.write_gexf(B, gexf_path)

    print("\n[BIPARTITE EXPORT]")
    print(f"Input: {Path(INPUT_PATH).resolve()}")
    print(f"Books: {len(books):,}")
    print(f"Tropes: {len(trope_cols):,}")
    print(f"Edges (incidences): {B.number_of_edges():,}")
    print(f"→ Wrote: {gexf_path.resolve()}")

    # -------------------------
    # Pairwise overlap CSV
    # -------------------------
    # For each book pair:
    #   shared   = intersection
    #   unshared = symmetric difference
    #
    # To compute this efficiently, we pre-build trope sets per book.
    trope_sets = {}
    for book_label, row in zip(books, inc.itertuples(index=False, name=None)):
        present = {t for t, v in zip(trope_cols, row) if v}
        trope_sets[book_label] = present

    rows_out = []
    for a, b in combinations(books, 2):
        sA = trope_sets[a]
        sB = trope_sets[b]
        shared = sorted(sA & sB)
        unshared = sorted((sA | sB) - (sA & sB))
        rows_out.append(
            {
                "book_A": a,
                "book_B": b,
                "n_shared": len(shared),
                "shared_tropes": ";".join(shared),
                "n_unshared": len(unshared),
                "unshared_tropes": ";".join(unshared),
            }
        )

    pd.DataFrame(rows_out).to_csv(csv_path, index=False, encoding="utf-8")

    print("\n[PAIRWISE OVERLAP CSV]")
    print(f"Pairs: {len(rows_out):,}")
    print(f"→ Wrote: {csv_path.resolve()}\n")


if __name__ == "__main__":
    main()