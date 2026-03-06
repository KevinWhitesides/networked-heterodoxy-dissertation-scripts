# 03_similarity

Scripts for computing similarity measures derived from network or incidence data.

These tools typically operate on **binary incidence matrices**
(case × feature/trope), from which similarity measures or structural
statistics are derived.

These scripts form part of a broader toolkit for analyzing relationships within
binary incidence datasets (case × feature matrices). The repository is organized
into stages reflecting common analytical workflows:

- **similarity analysis** (this folder) identifies patterns of shared or divergent feature repertoires
- **network construction** builds graphs from those relationships
- **topological analysis** examines structural properties of those networks

Individual scripts can be used independently, but they are also designed to work
together as components of larger analytical pipelines.

## Analytical Questions

The scripts in this folder are designed to answer specific analytical
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

### 01_jaccard_similarity_heatmap.py

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

### 02_cluster_from_similarity_matrix.py

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

### 03_compare_case_pair_features.py

Compares the feature repertoires of **two specific cases** and reports:

- features unique to Case A
- features shared by both cases
- features unique to Case B

This script functions as a **close-comparison tool** for moving from broad similarity patterns to specific feature-level interpretation.

The script:

1. Reads a binary incidence matrix from `.xlsx` or `.csv`.
2. Identifies two user-specified cases.
3. Optionally filters features by minimum frequency across the full dataset.
4. Computes:
   - features unique to Case A
   - shared features
   - features unique to Case B
5. Exports:
   - a three-column comparison CSV
   - an optional Markdown report
   - a concise console summary

This tool is especially useful for interpreting why two cases cluster together, differ sharply, or occupy unexpected positions within the broader similarity structure.

---

### 04_significant_zero_overlap.py

Identifies **case pairs with completely non-overlapping feature repertoires**
and evaluates whether those absences are statistically unusual under a
**degree-preserving null model**.

While the basic non-overlap script identifies pairs that share no features,
this tool goes further by asking whether such absences are **more extreme
than expected given the overall distribution of features across the dataset**.

The script:

1. Reads a binary incidence matrix from `.xlsx` or `.csv`.
2. Optionally filters features by minimum global frequency.
3. Optionally filters cases by minimum number of present features.
4. Identifies all **observed zero-overlap case pairs**.
5. Generates randomized datasets using a **Curveball degree-preserving null model**, which preserves the number of features associated with each case and the overall feature distribution.
6. Estimates an **empirical probability** for each zero-overlap pair under the null model.
7. Applies **Benjamini–Hochberg false discovery rate (FDR) correction**.
8. Exports:

   - a CSV listing all observed zero-overlap pairs and their significance metrics
   - an `analysis_summary.txt` file documenting parameters and results of the run

The output CSV includes:

- the two cases forming each pair
- feature counts for each case
- the empirical probability of observing zero overlap (`p_emp`)
- FDR significance flags (for example `sig_0.05` and `sig_0.01`)

This tool helps distinguish between:

- **incidental non-overlap** caused by sparse feature distributions, and  
- **structurally meaningful absences** that are unlikely under the dataset’s overall structure.

The resulting table can be used directly for analysis or supplied to
network-building scripts to construct **absence networks** linking cases
that exhibit statistically significant non-overlap.

---

## Data Assumptions

Most scripts in this folder assume data structured as a **binary incidence matrix**:

- rows = cases (books, songs, etc.)
- columns = features/tropes
- presence marked by `"X"`
- absence left blank

This structure makes it possible to analyze patterns of shared and divergent feature repertoires across cases.