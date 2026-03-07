# 02_networks

This folder contains scripts for constructing network graphs from binary incidence matrices or from derived similarity analyses.

Networks are generated either as:

- **Projected one-mode networks** (feature × feature weighted co-occurrence)
- **Bipartite incidence networks** (case × feature)
- **Absence-derived networks** 
  - one-mode case × case significant zero-overlap networks
  - bipartite case × feature networks of the retained subset
- **Discourse-gradient networks**
  - bipartite case × feature networks constructed from intermediary chains linking zero-overlap cases
- **Topic-derived networks** (one-mode & bipartite)

These scripts assume a cleaned “no metadata” and "no totals" input matrix unless otherwise specified.

---

# Scripts

## 01_build_one_mode_projection.py

### Purpose

Constructs a weighted one-mode projection from a binary incidence matrix and exports thresholded networks suitable for Gephi.

### Input

- `.xlsx` or `.csv`
- Rows = cases (e.g., books, songs)
- Columns = features/tropes
- Presence marked with `"X"`
- No totals rows
- No metadata columns (recommended)

Optional safeguard:

DROP_COLUMNS = []

### Global Node Filter

Applies `MIN_NODE_FREQ` (default = 2) prior to projection.

This removes features appearing in fewer than two cases, ensuring recurrence.

### Edge Thresholds

For each value in `EDGE_THRESHOLDS`, the script:

- Retains edges with co-occurrence ≥ threshold
- Builds a weighted undirected graph
- Exports both:
  - Edge list CSV
  - GEXF network

### Node Attributes Added

- `frequency`
- `degree`
- `weighted_degree`

### Typical Use

Edit configuration variables at the top of the script, then run:

python build_one_mode_projection.py

Multiple thresholded graphs can be produced in a single run.

---

## 02_build_bipartite_network.py

### Purpose

Constructs a bipartite (case × feature) network directly from a binary incidence matrix and exports it in Gephi-ready format.

This preserves the original incidence structure without projecting it into a one-mode co-occurrence network.

The script also produces a pairwise comparison table identifying shared and unshared features between all case pairs.

### Input

- `.xlsx` or `.csv`
- Rows = cases (e.g., books, songs)
- Columns = features (tropes)
- Presence marked with `"X"`

By default the script assumes:

- The first `N_METADATA_COLS` columns contain metadata
- Feature columns begin immediately afterward

Example structure:

| Source Title | Author | Year | Publisher | Plato | Atlantis | Aztec |
|--------------|-------|------|-----------|-------|---------|------|
| Book A | ... | ... | ... | X | | X |
| Book B | ... | ... | ... | | X | X |

Configuration variables at the top of the script allow adjustment of:

- metadata column count
- presence token
- column containing case identifiers

### Outputs

#### 1. Bipartite network

Exports a GEXF graph:

- Nodes:
  - cases (e.g., books, songs)
  - features (tropes)
- Edges:
  - case–feature incidence
- Edge weights: none (binary incidence)

Node attributes include:

- `type` (`case` or `feature`)
- `bipartite` partition identifier

This network preserves the original dataset structure and can be used for:

- visualization
- bipartite projections
- two-mode network analysis

#### 2. Pairwise overlap table

Exports a CSV listing every case pair with:

- number of shared features
- list of shared features
- number of unshared features
- list of unshared features

This CSV file is primarily intended as a qualitative aid for exploring specific overlaps between cases.

### Typical Use

Edit configuration variables at the top of the script, then run:

python build_bipartite_network.py

The script will generate:

- a bipartite `.gexf` network
- a pairwise overlap `.csv`

---

## 03_build_absence_networks.py

Constructs network representations of **statistically significant zero-overlap relationships** between cases.

This script is designed to work downstream of the similarity analysis performed by:

03_similarity/04_significant_zero_overlap.py

While that script identifies pairs of cases that share **no features and whose absence of overlap is unlikely under a degree-preserving null model**, the present script converts those results into network structures suitable for exploration and visualization.

The script produces two complementary graphs.

### 1. Absence graph (case × case)

- Nodes represent cases (books, songs, etc.)
- Edges represent **statistically significant zero-overlap relationships**

This graph provides a structural overview of how cases diverge from one another within the dataset.

### 2. Bipartite graph of the retained subset (case × feature)

- Nodes represent both cases and features
- Edges represent feature presence in cases

Only cases participating meaningfully in the absence structure are retained.

Cases must have at least a configurable number of significant zero-overlap relationships (default: **two**).

Features are filtered to those appearing in at least a configurable number of retained cases (default: **two**).

This graph shows the **feature repertoires of the subset of cases that define the absence network**, making it possible to see which features cluster within different regions of the retained discourse field.

While the absence graph shows **which cases diverge**, the bipartite graph reveals **why they diverge**.

### Outputs

absence_graph_sig.gexf
bipartite_thr2.gexf
analysis_summary.txt

### Analytical role

This script forms the **network construction stage** of the absence-analysis workflow:

03_similarity/04_significant_zero_overlap.py
↓
02_networks/03_build_absence_networks.py

The first script identifies statistically meaningful absence relationships.  
The present script converts those results into network structures that allow the retained subset of cases to be explored visually and structurally.

---

## 04_build_discourse_gradient_network.py

Constructs network representations of **discourse gradients** linking cases that otherwise exhibit zero direct overlap.

This script is designed to work downstream of the gradient identification stage performed by:

03_similarity/05_find_discourse_gradients.py

While the similarity script identifies intermediary chains connecting zero-overlap cases, the present script converts a selected chain into network and similarity visualizations suitable for interpretation and exploration.

A discourse gradient is a sequence such as:

A → B → C → D → E

where:

- A and E share **no features**
- intermediate cases share overlapping subsets of features
- the chain forms a **mediated pathway across the discourse field**

### Networks Constructed

The script constructs a **bipartite case × feature network** from the selected gradient chain.

Features are filtered to those appearing in at least a configurable number of cases within the chain (default: **two**), reducing noise while preserving shared conceptual structure. Two is generally recommended as it eliminates all features that only appear in a single case and preserves all features shared by at least two cases and thus showing how disconnected cases are conceptually bridged by mediating ones.

Book titles are automatically shortened to their **main titles (text before any colon)** when generating node labels, ensuring that graphs remain readable and node IDs are easier to reference within Gephi filters.

### Additional Analytical Outputs

The script also produces similarity diagnostics for the selected gradient:

- subset **Jaccard similarity matrix**
- ranked **pairwise similarity table**
- **heatmap visualization**

These outputs provide quick confirmation that the chain behaves as expected, with similarity gradually shifting from one endpoint to the other.

### Outputs

gradient_bipartite.gexf
gradient_jaccard_subset.csv
gradient_jaccard_pairs_ranked.csv
gradient_jaccard_heatmap.png
analysis_summary.txt

### Analytical role

This script forms the **network construction stage** of the discourse-gradient workflow:

03_similarity/05_find_discourse_gradients.py
↓
02_networks/04_build_discourse_gradient_network.py

The first script identifies candidate intermediary chains connecting disjoint cases.  
The present script converts those chains into graph structures that allow the mediated discourse relationships to be explored visually.

The resulting bipartite graph can be opened directly in **Gephi** or other network analysis software for further exploration.

Endpoint comparisons can be visualized in Gephi using the union-of-ego-networks filter (see instructions below).

## Visualizing Gradient Endpoints in Gephi

When exploring a discourse gradient network in **Gephi**, it is often useful to isolate the
two endpoint cases (A and E) in order to emphasize that they share **no direct overlap**.

Rather than generating a separate graph, this can be done directly within Gephi by filtering
the existing network.

### Procedure

1. Open the gradient `.gexf` network in **Gephi**.

2. In the **Filters** panel:

   - Open **Operator → UNION**
   - Drag **UNION** into the **Queries** workspace.

3. Under the UNION operator:

   - Drag **Topology → Ego Network** into the UNION box.
   - Drag a **second Ego Network** into the UNION box.

4. Configure the two ego networks:

   **First Ego Network**
   - `Node ID`: *Book A*
   - `Depth`: `1`

   **Second Ego Network**
   - `Node ID`: *Book E*
   - `Depth`: `1`

5. Click **Filter**.

Gephi will display the **union of the two ego networks**, showing each endpoint and the
features connected to it. Because the endpoints share no features, the resulting graph
will appear as two disconnected clusters.

### Why this works

Depth-1 ego networks include:

- the selected node
- all nodes directly connected to it

Applying **UNION** to two ego networks therefore shows the **complete feature repertoires
of both endpoint cases**, making their lack of overlap immediately visible.

This approach preserves the **layout, colors, and positions** of the full gradient graph,
allowing the filtered view to function as a focused illustration of endpoint divergence.

---

## build_topic_network.py

(placeholder)