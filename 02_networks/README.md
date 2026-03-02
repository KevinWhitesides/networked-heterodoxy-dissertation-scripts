# 02_networks

This folder contains scripts for constructing network graphs from binary incidence matrices.

Networks are generated either as:

- Projected one-mode networks (item × item weighted co-occurrence)
- Bipartite networks (case × item)
- Topic-derived networks (one-mode & bipartite)

These scripts assume a cleaned “no metadata” input matrix unless otherwise specified.

---

## Scripts

### build_one_mode_projection.py

#### Purpose

Constructs a weighted one-mode projection from a binary incidence matrix and exports thresholded networks suitable for Gephi.

#### Input

- `.xlsx` or `.csv`
- Rows = cases (e.g., books, songs)
- Columns = items/tropes
- Presence marked with `"X"`
- No totals rows
- No metadata columns (recommended)

Optional safeguard: `DROP_COLUMNS = []`

#### Global Node Filter

Applies `MIN_NODE_FREQ` (default = 2) prior to projection.

This removes items appearing in fewer than two cases, ensuring recurrence.

#### Edge Thresholds

For each value in `EDGE_THRESHOLDS`, the script:

- Retains edges with co-occurrence ≥ threshold
- Builds a weighted undirected graph
- Exports both:
  - Edge list CSV
  - GEXF network

#### Node Attributes Added

- `frequency`
- `degree`
- `weighted_degree`

#### Typical Use

Edit configuration variables at the top of the script, then run:

`python build_one_mode_projection.py`

Multiple thresholded graphs can be produced in a single run.

---

## Notes

- Node filtering is applied globally before edge thresholding.
- Edge thresholding is applied per output graph.
- This script is dataset-agnostic and was used across multiple case studies (2012 literature corpus, hip hop corpus).

### build_bipartite_network.py
(placeholder)

### build_topic_network.py
(placeholder)