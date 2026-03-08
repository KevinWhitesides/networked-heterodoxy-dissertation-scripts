# Dissertation Resources: Networked Heterodoxy Tools

This module contains scripts, workflows, and documentation developed for computational analysis in the dissertation:

*Networks of Heterodoxy: Shared Dissent and the Dynamics of Counter-Discourse* by Kevin Whitesides (2026), University of California, Santa Barbara.

This toolkit analyzes the relational structure of cultural datasets represented as binary case × feature incidence matrices.
It identifies patterns of shared repertoires (similarity), structural disjunctions (absence), and mediated pathways (gradients) between cases and features.

Scripts are organized **by methodological task rather than dataset**, allowing them to be reused across multiple case studies.

---

## Contents

- [Repository Structure](#repository-structure)
- [Data Format Assumptions](#data-format-assumptions)
- [Installation](#installation)

---

## Repository Structure

- `01_diagnostics/` — Threshold and structural diagnostics for calibrating network construction.
- `02_networks/` — Construction of one-mode and bipartite networks, similarity matrices, and networks derived from topic models.
- `03_metrics/` — Network metric analysis including brokerage, centrality, and structural measurements.
- `04_topic_modeling/` — MALLET pipelines, pyLDAvis visualizations, and topic dendrogram construction.
- `docs/` — Methodological notes, data format specifications, and supporting documentation.
- `workflows/` — Descriptions of how scripts were applied in specific case studies (e.g., the 2012 literature corpus and the Five Percenter Hip Hop corpus).

---

## Toolkit Workflows

The diagram below illustrates the analytical workflows supported by the Networked Heterodoxy toolkit.

[![Networked Heterodoxy Toolkit Workflows](workflows/networked_heterodoxy_workflows.png)](workflows/networked_heterodoxy_workflows.png)

---

## Glossary

The scripts in this repository analyze patterns of shared and divergent **features within cultural datasets**.  
The toolkit is designed to map relational structure--including similarity, structural absence, and mediated gradients--across collections of cultural artifacts such as books, songs, documents, or other textual sources.
Together these analyses allow researchers to map clusters, boundaries, and conceptual pathways within discourse fields.

The terms below describe the core analytical concepts used throughout the repository.

---

# Core Data Concepts

## Case

The primary unit of analysis in the dataset. A **case** represents an individual cultural artifact or source. Examples include:

- books  
- songs  
- articles  
- speeches  
- documents  
- videos  
- interviews  
- social media posts  

Cases form the **rows** of the dataset’s binary incidence matrix.

---

## Feature

A coded attribute that may appear within cases. *Features* represent elements that can be tagged or identified within cases.  
In the context of the *networked heterodoxy* project, features are typically referred to as **tropes**. Examples include:

- conceptual tropes  
- themes  
- named entities  
- references  
- ideas  
- motifs  
- topics  

Features form the **columns** of the binary incidence matrix.

---

## Binary Incidence Matrix (Case × Feature)

The fundamental data structure used throughout the toolkit.

Rows represent **cases** and columns represent **features**.

Each cell indicates whether a feature appears within a case.

Example:

| Case | Feature A | Feature B | Feature C |
|-----|-----|-----|-----|
| Case 1 | X | | X |
| Case 2 | | X | |
| Case 3 | X | X | |

Presence is typically encoded as:

- `"X"`
- `1`

Absence is encoded as:

- blank  
- `0`

This structure forms the foundation for all similarity, absence, and network analyses performed by the scripts.

---

## Feature Repertoire

The set of features associated with a particular case.

Example:

If a book contains the tropes:

- Plato  
- Atlantis  
- Lost Civilization  

then those features constitute the book’s **feature repertoire**.

Comparing feature repertoires across cases allows researchers to examine:

- conceptual similarity  
- divergence  
- mediation  
- discourse structure  

---

# Overlap and Similarity

## Co-occurrence

A relationship in which two **features** appear together in the same case.

Example:

If both **Atlantis** and **Plato** appear in a book, those features **co-occur**.

Co-occurrence counts are commonly used to construct **feature × feature networks**.

---

## Overlap

A relationship in which two **cases** share one or more features.

Example:

If two books both reference **Atlantis**, they exhibit feature **overlap**.

Overlap forms the basis for most case similarity metrics.

---

## Jaccard Similarity

A similarity measure used to compare the feature repertoires of two cases.

J(A,B) = |A ∩ B| / |A ∪ B|

Where:

- **A** = feature set of case A  
- **B** = feature set of case B  
- **|A ∩ B|** = number of features shared by both cases  
- **|A ∪ B|** = total number of distinct features used by either case  

Jaccard similarity therefore measures the **proportion of shared features relative to the total feature repertoire used by either case**.

Because the metric ignores shared absences, it is particularly well suited for **sparse cultural datasets** in which most features appear in only a small number of cases.

Jaccard similarity ranges from **0** (no shared features) to **1** (identical feature repertoires).

---

## Pairwise Similarity Matrix

A table listing similarity scores for every pair of cases.

Example:

| Case | Case A | Case B | Case C |
|-----|-----|-----|-----|
| Case A | 1.0 | 0.25 | 0.10 |
| Case B | 0.25 | 1.0 | 0.40 |
| Case C | 0.10 | 0.40 | 1.0 |

These matrices are often used as input for:

- clustering  
- similarity heatmaps  
- network construction  

---

# Absence and Disjunction

## Zero-Overlap Pair

A pair of cases that share **no features in common**.

Example:

If Book A uses features `{Plato, Atlantis}` and Book B uses `{Mayan Calendar, Aztec Myth}`, the two books form a **zero-overlap pair**.

Such relationships indicate **maximal divergence in feature repertoires**.

---

## Significant Zero-Overlap

A zero-overlap relationship that occurs **less often than expected under a randomized version of the dataset**.

Statistical testing determines whether the absence of shared features is unusually strong given:

- the number of features used by each case  
- the overall distribution of features across the dataset  

This helps distinguish between:

- **incidental absence** caused by sparse data  
- **structural disjunction** reflecting meaningful conceptual separation  

---

## Feature Non-Co-Occurrence

The feature-level analogue of zero-overlap.

Two features **never co-occur** if they never appear together in any case.

Feature absence analysis identifies feature pairs that are:

- mutually exclusive  
- structurally separated within the dataset  

---

# Null Models and Statistical Testing

## Null Model

A randomized version of the dataset used to estimate expected patterns.

Null models allow researchers to determine whether observed patterns differ from what would occur by chance.

---

## Degree-Preserving Null Model

A randomization method that preserves:

- the number of features associated with each case  
- the number of cases associated with each feature  

while randomizing their associations.

This ensures statistical tests account for the dataset’s structural constraints.

---

## Curveball Algorithm

A method for generating degree-preserving randomizations of binary incidence matrices.

The algorithm repeatedly swaps feature lists between cases while preserving:

- row totals  
- column totals  

This produces realistic randomized datasets for statistical testing.

---

## Empirical Probability (`p_emp`)

The proportion of randomized datasets in which a particular pattern occurs.

Example:

p_emp = 0.01

Lower values indicate stronger statistical significance.

---

## False Discovery Rate (FDR)

A statistical correction used when performing many simultaneous tests.

FDR controls the expected proportion of false positives among results identified as significant.

Typical flags include:

- `sig_0.05`  
- `sig_0.01`  

---

# Network Structures

## Network (Graph)

A mathematical representation consisting of:

- **nodes** (entities)  
- **edges** (relationships)

Networks are used to analyze structural relationships among cases or features.

---

## Bipartite Network (Case × Feature)

A network containing two distinct types of nodes:

- cases  
- features  

Edges connect cases to the features they contain.

Example:

```
Book A — Plato
Book A — Atlantis
Book B — Atlantis
```

This representation preserves the **original structure of the dataset**.

---

## One-Mode Network (Projection)

A network derived from a bipartite structure but that contains only one node type.

Examples include:

### Case × Case Networks

All nodes represent cases.  
Edges represent similarity based on shared features.

### Feature × Feature Networks

All nodes represent features.  
Edges represent co-occurrence within cases.

---

## Projection

The process of converting a bipartite network into a one-mode network.

---

# Gradient and Mediation Concepts

## Case Gradient

A sequence of cases that indirectly connects two otherwise non-overlapping cases.

Example:

A ↔ B ↔ C ↔ D ↔ E

where:

- A and E share **no features**  
- intermediate cases share overlapping subsets of features  

Case gradients reveal **mediated pathways across the discourse field**.

---

## Feature Gradient

The feature-level analogue of a case gradient.

A sequence of features that indirectly connects two features that never co-occur.

Example:

Feature A ↔ Feature B ↔ Feature C ↔ Feature D ↔ Feature E

where:

- A and E never occur in the same case  
- intermediate features share overlapping case distributions  

Feature gradients reveal **chains of conceptual mediation across the dataset**.

---

## Mediating Case

A case that connects otherwise disjoint parts of the feature space.

In a case gradient:

A ↔ B ↔ C ↔ D ↔ E

cases **B, C, and D** act as intermediaries linking the endpoints of cases A and E.

---

## Mediating Feature

A feature that connects otherwise separated feature regions.

Example:

Ancient Astronauts ↔ Zecharia Sitchin ↔ Mesopotamian Religion

Intermediate features create conceptual bridges across otherwise separate discourse clusters.

---

# Structural Network Analysis

## Topological Analysis

Network methods that examine the **connectivity structure of a graph**—how nodes are linked to one another independent of visual layout or geometry.

Topological analysis focuses on patterns of connection within a network, including how clusters form, how information flows, and which nodes bridge otherwise separated regions.

Common topological measures include:

- degree distribution  
- connected components  
- k-core and k-component structure  
- shortest paths  
- betweenness centrality  
- brokerage metrics such as **constraint** and **effective size**

Topological analysis in this repository is applied to both:

- **case networks** (relationships between sources based on shared features)
- **feature networks** (relationships between tropes based on co-occurrence across cases)  

---

## Brokerage

A structural role in which a node connects otherwise separated parts of a network.

Broker nodes often facilitate:

- information flow  
- conceptual mediation  
- structural integration  

---

## Constraint

A network measure introduced by Ronald Burt.

Constraint measures how strongly a node’s connections are concentrated within a tightly connected neighborhood.

- **High constraint** ↔ node embedded in dense cluster  
- **Low constraint** ↔ node bridges different regions of the network  

---

## Effective Size

Another brokerage metric introduced by Ronald Burt.

Effective size measures how many **non-redundant connections** a node has.

Higher effective size indicates stronger brokerage potential.

---

# Interpretation Concepts

## Discourse Space (or Field)

The broader conceptual space defined by relationships among cases and features.

Networks, gradients, and absence structures help map this field.

---

## Structural Divergence

A condition in which cases or features occupy distinct regions of the discourse field.

Absence networks often highlight such divergence.

---

## Mediated Continuity

The phenomenon in which apparently disconnected cases or features remain indirectly linked through intermediate elements.

Gradient analysis reveals these hidden pathways across discourse structures.

---

## Data Format Assumptions

Most network scripts assume input in the form of a **binary incidence matrix** — a spreadsheet representing relationships between cases and features.

Typical structure:

- Rows = cases (books, songs, etc.)
- Columns = tropes, topics, or features
- Presence indicated by `"X"`
- Absence left blank

From this matrix, the scripts construct:

- bipartite case × trope networks
- projected one-mode trope × trope networks
- co-occurrence matrices
- network metrics and structural diagnostics

---

## Installation

Python **3.9+** recommended.

Install dependencies with:

```bash
pip install -r requirements.txt