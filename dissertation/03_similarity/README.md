# 03_metrics

Scripts for computing structural and similarity measures derived from network or incidence data.

These tools typically operate on **binary incidence matrices**
(case × feature/trope), from which similarity measures or structural
statistics are derived.

## Analytical Focus

The scripts in this folder are designed to answer specific research
questions about relationships within binary incidence datasets
(case × feature/trope matrices).

| Metric | Research question |
|------|-------------------|
| **Jaccard similarity** | Which cases have similar feature repertoires? |
| **Hierarchical clustering** | Which groups of cases exhibit similar feature repertoires, and how tightly do those clusters hold together? |
| **Brokerage (Burt’s metrics)** | Which nodes connect otherwise separate clusters or discourse regions? |
| **Non-overlap detection** | Which pairs of cases have completely non-overlapping repertoires? |
| **Discourse gradient identification** | Which intermediary cases link otherwise non-overlapping cases within the broader network? |

These measures help identify patterns of similarity, mediation, and
distinctiveness within cultural datasets.

---

## Current Scripts

### jaccard_similarity_heatmap.py

Computes pairwise **Jaccard similarity** between cases based on shared feature/trope presence.

The script:

1. Reads a binary incidence matrix from `.xlsx` or `.csv`.
2. Optionally filters features appearing in fewer than a specified number of cases (default: ≥2).
3. Computes a case × case Jaccard similarity matrix.
4. Exports:

   - a CSV similarity matrix  
   - a heatmap visualization (PNG)

Jaccard similarity measures overlap in **feature repertoires** while ignoring shared absences, making it well suited for sparse cultural feature datasets.

---

### cluster_from_similarity_matrix.py

Performs **hierarchical clustering** on a similarity matrix (such as the output of the Jaccard script) in order to identify groups of cases with similar feature repertoires.

The script:

1. Reads a case × case similarity matrix from CSV.
2. Converts similarity values to distances (`distance = 1 − similarity`).
3. Performs hierarchical clustering using a configurable linkage method.
4. Assigns cases to clusters either:
   - by specifying a fixed number of clusters, or
   - by applying a distance threshold.
5. Exports:

   - cluster assignments for each case (CSV)
   - average intra-cluster similarity statistics
   - similarity of each case to the other members of its cluster
   - optional dendrogram visualization

This script formalizes patterns visible in similarity heatmaps by producing explicit **cluster structures** and diagnostic summaries of cluster cohesion.

---

## Data Assumptions

Most scripts in this folder assume data structured as a **binary incidence matrix**:

- rows = cases (books, songs, etc.)
- columns = features/tropes
- presence marked by `"X"`
- absence left blank

This structure makes it possible to analyze patterns of shared and divergent feature repertoires across cases.