# 04_topology

Scripts for analyzing the **structural topology of networks**.

Unlike similarity analysis (which compares repertoires of features across
cases), topology analysis examines the **connectivity structure of the
network itself**.

Scripts in this folder operate on network structures.

Some scripts read networks directly from `.gexf` files produced by the
`02_networks/` scripts, while others construct a network internally from
binary incidence matrices.

---

## Analytical Focus

These topology analyses ask questions about **how robustly parts of a network
hold together** and which nodes occupy structurally central positions.

| Method | Research question |
|------|-------------------|
| **k-components** | Which groups of nodes remain connected even if multiple nodes are removed? |
| **k-core decomposition** | How deeply embedded is each node within the overall network structure? |

These two measures describe **different aspects of structural cohesion**.

---

### k-components

k-component analysis identifies **cohesive subgraphs** that require the
removal of at least *k* nodes to disconnect them.

Higher *k* values indicate:

- stronger structural cohesion
- greater redundancy of connections
- tightly integrated clusters of nodes

In discourse networks, k-components can reveal **robust thematic clusters**
that remain connected even if key tropes or concepts are removed.

---

### k-core decomposition

A k-core identifies nodes that remain after recursively removing nodes with
degree less than *k*.

The **core number** of a node indicates the deepest k-core in which that
node appears.

Core numbers therefore measure **node embeddedness**, identifying nodes that
are structurally central to the network.

---

### Seeing Both Together

Used together, these measures reveal complementary aspects of network structure:

- **k-components** identify *cohesive clusters of nodes*
- **k-core numbers** identify *structurally central nodes*

This combination helps distinguish between:

- clusters that are **structurally robust as a group**
- nodes that sit at the **center of dense regions of the network**, and

---

## Relationship to Gephi

Gephi includes built-in tools for **k-core decomposition**.

This script supplements Gephi by:

- computing **k-components**, which Gephi does not provide
- exporting **k-core numbers** for direct comparison
- exporting individual **k-component subgraphs** for visualization in Gephi

This makes it possible to analyze structural cohesion computationally while
still exploring the resulting networks visually.

---

## Current Scripts

### k_components_from_gexf.py

Computes **k-components** and **k-core numbers** from an existing network file.

Input:

- `.gexf` network file
- typically produced by scripts in `02_networks/`

The script:

1. Reads a network graph from GEXF.
2. Computes k-core numbers for all nodes.
3. Computes k-components of the graph.
4. Exports:

   - node-level **k-core numbers**
   - node-level **degree summaries**
   - **GEXF subgraphs** for each k-component
   - a **summary table** listing all components

The exported GEXF component graphs can be opened directly in Gephi for visualization, while accompanying CSV files provide tabular summaries of nodes and component structure.
---

## Data Assumptions

Scripts in this folder assume that the input network:

- is stored as a **GEXF graph**
- represents a previously constructed network (e.g., trope co-occurrence)
- may be generated using the scripts in `02_networks/`

Topology analysis therefore represents a **downstream step** following
network construction.