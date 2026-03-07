# Dissertation Resources: Networked Heterodoxy Tools

This module contains scripts, workflows, and documentation developed for computational analysis in the dissertation:

*Networks of Heterodoxy: Shared Dissent and the Dynamics of Counter-Discourse* by Kevin Whitesides (2026), University of California, Santa Barbara.

The tools support the analysis of **structured cultural datasets**, including binary incidence matrices and topic-model outputs, enabling the construction and analysis of co-occurrence networks, bipartite graphs, and related structures.

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

## Glossary

The scripts in this repository analyze patterns of shared and divergent
**features within cultural datasets** (such as books, songs, or documents).
The terms below describe the core analytical concepts used throughout the toolkit.

**Case**  
The primary unit of analysis in the dataset: "sources" or "texts" (broadly conceived).  
Examples include books, songs, documents, or other cultural artifacts.

**Feature**  
A coded attribute or element that may appear within cases. In networked heterodoxy, these are typically called tropes.  
Examples include tropes, topics, entities, or other tagged concepts.

**Binary incidence matrix (case × feature)**  
A table in which rows represent cases and columns represent features.  
Cells indicate whether a feature appears in a case (e.g., `"X"` or `1` for presence, blank or `0` for absence).

**Feature repertoire**  
The set of features associated with a given case.  
Comparing feature repertoires allows researchers to analyze similarity, divergence, and structural relationships between cases.

**Co-occurrence**  
A relationship in which two features appear together within the same case.  
Co-occurrence counts are commonly used to construct **feature × feature networks**.

**Bipartite network (case × feature)**  
A two-mode network containing two types of nodes: cases and features.  
Edges represent the presence of a feature within a case.

**Projected network (one-mode network)**  
A network derived from a bipartite structure in which nodes represent only one type of entity.  
Examples include:
- **case × case networks**, based on shared features  
- **feature × feature networks**, based on co-occurrence within cases

**Similarity measure**  
A metric used to quantify how similar two cases are based on their feature repertoires.  
For example, **Jaccard similarity** measures the proportion of shared features relative to the total features used by either case.

**Absence relationship (zero-overlap pair)**  
A pair of cases that share **no features in common**.  
Absence analysis identifies such cases and examines whether such zero-overlap relationships occur more often than expected under a random model.

**Null model**  
A randomized version of the dataset used to estimate expected patterns under controlled conditions.  
In this repository, degree-preserving null models maintain the number of features associated with each case while randomizing their distribution.

**Structural analysis**  
Network methods that examine the organization of nodes and edges within a graph.  
Examples include k-core decomposition, k-component analysis, and brokerage metrics.

**Brokerage**  
A structural network role in which a node connects otherwise weakly connected or separated parts of a network.  
Nodes with strong brokerage positions can facilitate the flow of information between different clusters or discourse regions.

**Constraint**  
A network measure developed by Ronald Burt that quantifies how strongly a node’s connections are concentrated within a tightly connected neighborhood.  
High constraint indicates that a node’s contacts are highly interconnected, limiting its ability to broker between different parts of the network.

**Effective size**  
A brokerage-related metric introduced by Ronald Burt that measures how many **non-redundant connections** a node has in its network neighborhood.  
Higher effective size indicates that a node connects to more structurally independent neighbors and therefore occupies a stronger brokerage position.

**Discourse gradient**  
A sequence of cases that indirectly connects two otherwise non-overlapping cases through intermediate cases that share features with one another.  
Discourse gradients reveal how seemingly disconnected cases may still participate in a broader small-world structure of shared features.

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