# 02_networks

This folder contains scripts for constructing network graphs from binary incidence matrices or from derived similarity analyses.

Networks are generated either as:

- **Projected one-mode networks** (feature × feature weighted co-occurrence)
- **Bipartite incidence networks** (case × feature)
- **Absence-derived networks**
  - one-mode case × case significant zero-overlap networks
  - bipartite case × feature networks of the retained subset
- **Gradient-derived networks**
  - case-gradient networks (case → case mediated through shared features)
  - feature-gradient networks (feature → feature mediated through shared cases)
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

03_similarity/04_significant_zero_case_overlap.py

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

03_similarity/04_significant_zero_case_overlap.py
↓
02_networks/03_build_absence_networks.py

The first script identifies statistically meaningful absence relationships.  
The present script converts those results into network structures that allow the retained subset of cases to be explored visually and structurally.

---

## 04_build_discourse_gradient_network.py

Constructs network representations of **case gradients** linking cases that otherwise exhibit zero direct overlap.

This script is designed to work downstream of the gradient identification stage performed by:


03_similarity/05_find_case_gradients.py


While the similarity script identifies intermediary chains connecting zero-overlap cases, the present script converts a selected chain into network and similarity visualizations suitable for interpretation and exploration.

A case gradient is a sequence such as:

A → B → C → D → E

where:

- A and E share **no features**
- intermediate cases share overlapping subsets of features
- the chain forms a **mediated pathway across the discourse field**

### Networks Constructed

The script constructs a **bipartite case × feature network** from the selected gradient chain.

Features are filtered to those appearing in at least a configurable number of cases within the chain (default: **two**), reducing noise while preserving shared conceptual structure.

Book titles are automatically shortened to their **main titles (text before any colon)** when generating node labels, ensuring that graphs remain readable and node IDs are easier to reference within Gephi filters.

### Additional Analytical Outputs

The script also produces similarity diagnostics for the selected gradient:

- subset **Jaccard similarity matrix**
- ranked **pairwise similarity table**
- **heatmap visualization**

### Outputs

gradient_bipartite.gexf
gradient_jaccard_subset.csv
gradient_jaccard_pairs_ranked.csv
gradient_jaccard_heatmap.png
analysis_summary.txt

### Analytical role

This script forms the **network construction stage** of the case-gradient workflow:

03_similarity/05_find_case_gradients.py
↓
02_networks/04_build_discourse_gradient_network.py

The first script identifies candidate intermediary chains connecting disjoint cases.  
The present script converts those chains into graph structures that allow the mediated discourse relationships to be explored visually.

---

## 05_build_feature_absence_network.py

Constructs network representations of **statistically significant zero-overlap relationships between features**.

This script is designed to work downstream of the similarity analysis performed by:

03_similarity/06_significant_zero_feature_overlap.py

While that script identifies feature pairs that never co-occur in the same case and evaluates whether those absences are unlikely under a degree-preserving null model, the present script converts those results into network structures suitable for exploration and visualization.

The script produces two complementary graphs.

### 1. Feature absence graph (feature × feature)

- Nodes represent features (tropes)
- Edges represent **statistically significant zero-overlap relationships**

This graph provides a structural overview of how feature repertoires diverge across the dataset.

### 2. Bipartite graph of the retained subset (case × feature)

- Nodes represent both cases and features
- Edges represent feature presence in cases

Only features participating meaningfully in the absence structure are retained.

Features must have at least a configurable number of significant zero-overlap neighbors (default: **two**).

Cases are retained if they contain at least a configurable number of those retained features (default: **one**).

This graph reveals the **cases that support the mutually exclusive feature regions**, allowing inspection of the corpus structure underlying the absence network.

### Outputs

feature_absence_graph_sig.gexf  
feature_absence_bipartite.gexf  
analysis_summary.txt

### Analytical role

This script forms the **network construction stage** of the feature-absence workflow:

03_similarity/06_significant_zero_feature_overlap.py  
↓  
02_networks/05_build_feature_absence_network.py

The first script identifies statistically meaningful feature disjunctions.  
The present script converts those results into graph structures that allow the retained feature regions and their supporting cases to be explored visually.

---

## 06_build_feature_gradient_networks.py

Constructs network representations of **feature gradients** linking features that never directly co-occur.

This script is designed to work downstream of the feature-gradient identification stage performed by:

03_similarity/07_find_feature_gradients.py

While the similarity script identifies intermediary chains connecting non-co-occurring features, the present script converts a selected feature gradient into network and similarity visualizations suitable for interpretation.

A feature gradient is a sequence such as:

Feature A → Feature B → Feature C → Feature D → Feature E

where:

- Feature A and Feature E **never occur in the same case**
- intermediate features share overlapping case distributions
- the chain forms a **mediated pathway across feature space**

### Networks Constructed

The script constructs a **bipartite feature × case network** from the selected gradient chain.

In this network:

- **features are the focal nodes**
- **cases are the supporting nodes**

Edges represent the presence of a feature within a case.

By default, cases must contain **at least two of the gradient features** (`MIN_GRADIENT_FEATURES_PER_CASE = 2`) in order to be retained. This removes cases that only contain a single feature and therefore do not help mediate the gradient.

Case titles may optionally be shortened automatically through configuration settings in the script to improve graph readability.

### Additional Analytical Outputs

The script also produces diagnostic similarity outputs for the selected feature gradient:

- subset **feature × feature Jaccard matrix**
- ranked **pairwise similarity table**
- **heatmap visualization**

These outputs provide a compact summary of how strongly the gradient features overlap in their case distributions.

### Outputs

feature_gradient_bipartite.gexf  
feature_gradient_jaccard_subset.csv  
feature_gradient_jaccard_pairs_ranked.csv  
feature_gradient_jaccard_heatmap.png  
analysis_summary.txt

### Analytical role

This script forms the **network construction stage** of the feature-gradient workflow:

03_similarity/07_find_feature_gradients.py  
↓  
02_networks/06_build_feature_gradient_networks.py

The first script identifies intermediary feature chains connecting non-co-occurring features.  
The present script converts those chains into graph structures that reveal **the cases that mediate those conceptual connections**.

---

## build_topic_network.py

(placeholder)