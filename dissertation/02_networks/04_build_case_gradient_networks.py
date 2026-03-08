#!/usr/bin/env python3
"""
04_build_case_gradient_networks.py

Build network and diagnostic outputs for a selected discourse gradient.

Outputs:
    gradient_bipartite.gexf
    gradient_jaccard_subset.csv
    gradient_jaccard_pairs_ranked.csv
    gradient_jaccard_heatmap.png
    analysis_summary.txt
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
from itertools import combinations

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

GRADIENTS_CSV = Path("discourse_gradients.csv")
INCIDENCE_PATH = Path("input_incidence_matrix.xlsx")
SHEET_NAME = 0

CASE_ID_COLUMN = "Source Title"
N_METADATA_COLS = 4
PRESENCE_TOKEN = "X"

SELECTION_MODE = "row"
SELECTED_ROW = 0
EXACT_CHAIN_STRING = ""

MIN_CASES_FOR_FEATURE = 2

OUTPUT_DIR = Path("gradient_output")
OUTPUT_DIR.mkdir(exist_ok=True)

OUT_GEXF = "gradient_bipartite.gexf"
OUT_JACCARD_MATRIX = "gradient_jaccard_subset.csv"
OUT_JACCARD_PAIRS = "gradient_jaccard_pairs_ranked.csv"
OUT_HEATMAP = "gradient_jaccard_heatmap.png"
OUT_SUMMARY = "analysis_summary.txt"


# ------------------------------------------------------------
# TITLE SHORTENING
# ------------------------------------------------------------

def shorten_title(title: str):
    """
    Remove subtitle after colon.
    """
    short = title.split(":")[0].strip()
    return short


def ensure_unique_titles(titles):
    """
    Ensure shortened titles are unique.
    """
    seen = {}
    result = []

    for t in titles:
        base = shorten_title(t)

        if base not in seen:
            seen[base] = 1
            result.append(base)
        else:
            seen[base] += 1
            result.append(f"{base} [{seen[base]}]")

    return result


# ------------------------------------------------------------
# DATA LOADING
# ------------------------------------------------------------

def read_incidence_matrix(path):

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        df = pd.read_excel(path, sheet_name=SHEET_NAME, dtype=str)

    df = df.fillna("")
    return df


def binarize(df, feature_cols):

    def to_bin(x):
        if str(x).strip().lower() == PRESENCE_TOKEN.lower():
            return 1
        return 0

    return df[feature_cols].applymap(to_bin)


# ------------------------------------------------------------
# JACCARD
# ------------------------------------------------------------

def compute_jaccard_matrix(X):

    n = X.shape[0]
    mat = np.zeros((n, n))

    for i in range(n):
        for j in range(i, n):

            inter = np.bitwise_and(X[i], X[j]).sum()
            union = np.bitwise_or(X[i], X[j]).sum()

            jacc = inter / union if union > 0 else 0

            mat[i, j] = jacc
            mat[j, i] = jacc

    return mat


def build_ranked_pairs(X, titles):

    rows = []

    for i, j in combinations(range(len(titles)), 2):

        inter = np.bitwise_and(X[i], X[j]).sum()
        union = np.bitwise_or(X[i], X[j]).sum()

        jacc = inter / union if union > 0 else 0

        rows.append({
            "case_1": titles[i],
            "case_2": titles[j],
            "shared_features": inter,
            "union_features": union,
            "jaccard": jacc
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("jaccard", ascending=False)

    return df


# ------------------------------------------------------------
# HEATMAP
# ------------------------------------------------------------

def write_heatmap(matrix, labels, path):

    plt.figure(figsize=(8, 6))

    plt.imshow(matrix)
    plt.colorbar()

    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.yticks(range(len(labels)), labels)

    plt.title("Jaccard Similarity Within Gradient")

    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


# ------------------------------------------------------------
# BIPARTITE GRAPH
# ------------------------------------------------------------

def build_bipartite(subset_df, case_titles, feature_cols):

    trope_freq = subset_df[feature_cols].sum()

    keep_features = trope_freq[trope_freq >= MIN_CASES_FOR_FEATURE].index.tolist()

    G = nx.Graph()

    # Case nodes
    for full, short in case_titles.items():

        G.add_node(
            short,
            label=short,
            full_title=full,
            node_type="case"
        )

    # Feature nodes
    for feat in keep_features:

        G.add_node(
            feat,
            label=feat,
            node_type="feature"
        )

    # Edges
    for i, row in subset_df.iterrows():

        case = case_titles[row[CASE_ID_COLUMN]]

        for feat in keep_features:

            if row[feat] == 1:

                G.add_edge(case, feat)

    return G


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # --------------------------------------------------------
    # Load gradients
    # --------------------------------------------------------

    grad_df = pd.read_csv(GRADIENTS_CSV)

    if SELECTION_MODE == "row":
        row = grad_df.iloc[SELECTED_ROW]

    elif SELECTION_MODE == "chain":
        row = grad_df[grad_df["chain"] == EXACT_CHAIN_STRING].iloc[0]

    else:
        raise ValueError("Invalid SELECTION_MODE")

    chain = [c.strip() for c in row["chain"].split("|")]

    # --------------------------------------------------------
    # Load incidence matrix
    # --------------------------------------------------------

    df = read_incidence_matrix(INCIDENCE_PATH)

    feature_cols = list(df.columns[N_METADATA_COLS:])

    bin_df = binarize(df, feature_cols)

    df_bin = pd.concat([df[[CASE_ID_COLUMN]], bin_df], axis=1)

    # --------------------------------------------------------
    # Subset to gradient chain
    # --------------------------------------------------------

    subset = df_bin[df_bin[CASE_ID_COLUMN].isin(chain)].copy()

    subset = subset.set_index(CASE_ID_COLUMN).loc[chain].reset_index()

    # --------------------------------------------------------
    # Title shortening
    # --------------------------------------------------------

    full_titles = subset[CASE_ID_COLUMN].tolist()

    short_titles = ensure_unique_titles(full_titles)

    title_map = dict(zip(full_titles, short_titles))

    # --------------------------------------------------------
    # Build graph
    # --------------------------------------------------------

    G = build_bipartite(subset, title_map, feature_cols)

    nx.write_gexf(G, OUTPUT_DIR / OUT_GEXF)

    # --------------------------------------------------------
    # Jaccard matrix
    # --------------------------------------------------------

    X = subset[feature_cols].to_numpy(dtype=np.uint8)

    jaccard = compute_jaccard_matrix(X)

    jacc_df = pd.DataFrame(
        jaccard,
        index=short_titles,
        columns=short_titles
    )

    jacc_df.to_csv(OUTPUT_DIR / OUT_JACCARD_MATRIX)

    # --------------------------------------------------------
    # Ranked pair list
    # --------------------------------------------------------

    ranked = build_ranked_pairs(X, short_titles)

    ranked.to_csv(OUTPUT_DIR / OUT_JACCARD_PAIRS, index=False)

    # --------------------------------------------------------
    # Heatmap
    # --------------------------------------------------------

    write_heatmap(jaccard, short_titles, OUTPUT_DIR / OUT_HEATMAP)

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    with open(OUTPUT_DIR / OUT_SUMMARY, "w") as f:

        f.write("Gradient Network Construction Summary\n\n")
        f.write(f"Timestamp: {timestamp}\n\n")

        f.write("Selected chain:\n")
        f.write(" -> ".join(short_titles) + "\n\n")

        f.write(f"Cases: {len(short_titles)}\n")
        f.write(f"Features retained: {len(feature_cols)}\n")
        f.write(f"Edges: {G.number_of_edges()}\n")

    print("✓ Gradient network built")
    print("Chain:", " -> ".join(short_titles))


if __name__ == "__main__":
    main()