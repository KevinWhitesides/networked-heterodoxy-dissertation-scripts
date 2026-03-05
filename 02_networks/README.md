# 02_networks

This folder contains scripts for constructing network graphs from binary incidence matrices.

Networks are generated either as:

- Projected one-mode networks (item × item weighted co-occurrence)
- Bipartite incidence networks (case × item)
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

#### Purpose

Constructs a bipartite (case × item) network directly from a binary incidence matrix and exports it in Gephi-ready format.

This preserves the original incidence structure without projecting it into a one-mode co-occurrence network.

The script also produces a pairwise comparison table identifying shared and unshared items between all case pairs.

#### Input

- `.xlsx` or `.csv`
- Rows = cases (e.g., books, songs)
- Columns = items/tropes
- Presence marked with `"X"`

By default the script assumes:

- The first `N_METADATA_COLS` columns contain metadata
- Item columns begin immediately afterward

Example structure:

| Source Title | Author | Year | Publisher | Plato | Atlantis | Aztec |
|--------------|--------|------|-----------|-------|----------|-------|
| Book A | ... |  ....  | .... |   ......  |   X   |          |   X   |
| Book B | ... |  ....  | .... |   ......  |       |    X     |   X   |

Configuration variables at the top of the script allow adjustment of:

- metadata column count
- presence token
- column containing case identifiers

#### Outputs

**1. Bipartite network**

Exports a GEXF graph:

- Nodes:
  - cases (e.g., books, songs)
  - items/tropes
- Edges:
  - case–item incidence
- Edge weights: none (binary incidence)

Node attributes include:

- `type` (`case` or `item`)
- `bipartite` partition identifier

This network preserves the original dataset structure and can be used for:

- visualization
- bipartite projections
- two-mode network analysis

**2. Pairwise overlap table**

Exports a CSV listing every case pair with:

- number of shared items
- list of shared items
- number of unshared items
- list of unshared items

This CSV file is primarily intended as a qualitative aid for exploring specific overlaps between cases.

#### Typical Use

Edit configuration variables at the top of the script, then run:

`python build_bipartite_network.py`

The script will generate:

- a bipartite `.gexf` network
- a pairwise overlap `.csv`

### build_topic_network.py
(placeholder)