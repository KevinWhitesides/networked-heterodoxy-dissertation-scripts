# 01_diagnostics

This folder contains scripts for calibrating network construction parameters prior to graph generation.

## 01_diagnose_cooccurrence_thresholds.py

### Purpose

Evaluates how different edge-weight thresholds affect the structure of a projected one-mode co-occurrence network derived from a binary incidence matrix.

For each edge-weight threshold, the script reports:

- Number of qualifying edges (co-occurrence ≥ threshold)
- Number of surviving nodes (tropes participating in at least one qualifying edge)
- Total possible pairs among surviving nodes
- Edge density among surviving nodes

### Rationale

Edge thresholds substantially alter network size, density, and interpretability.  
This diagnostic allows threshold selection to be justified empirically rather than chosen arbitrarily.

The goal is to identify the point at which low-frequency or incidental co-occurrence gives way to more stable and recurrent relational structure.

### Input Requirements

- Binary incidence matrix
- Rows = cases (e.g., books, songs)
- Columns = tropes/features
- Presence marked with `"X"`
- Absence left blank
- No metadata columns (no author/artist, title, year, publisher, etc. columns)
- No totals rows or columns

Excel (`.xlsx`) or CSV formats supported (edit script as needed).

### Output

This script prints a summary table to the console **and** writes a timestamped CSV file (saved in the same directory as the script by default) containing:

- `threshold`
- `nodes_surviving`
- `edges_qualifying`
- `possible_pairs`
- `density_surviving_nodes`

This makes threshold calibration results easy to archive and cite (e.g., in appendices or a reproducibility repository).

### Typical Use

Run `python diagnose_cooccurrence_thresholds.py` prior to building a projected one-mode network.

Use output to select an edge threshold appropriate for network construction.

Note: This diagnostic applies to projected one-mode networks; bipartite case–trope networks do not require edge-weight threshold calibration.