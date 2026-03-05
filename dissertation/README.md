\# Dissertation Resources: Networked Heterodoxy Tools



This module contains scripts, workflows, and documentation used in the computational analysis for the dissertation:



\*Networks of Heterodoxy: Shared Dissent and the Dynamics of Counter-Discourse.\*



The tools support the analysis of \*\*structured cultural datasets\*\*, including binary incidence matrices and topic-model outputs, enabling the construction and analysis of co-occurrence networks, bipartite graphs, and related structures.



Scripts are organized \*\*by methodological task rather than dataset\*\*, allowing them to be reused across multiple case studies.



---



\## Contents



\- \[Repository Structure](#repository-structure)

\- \[Data Format Assumptions](#data-format-assumptions)

\- \[Installation](#installation)



---



\## Repository Structure



\- `01\_diagnostics/` — Threshold and structural diagnostics for calibrating network construction.



\- `02\_networks/` — Construction of one-mode and bipartite networks, similarity matrices, and networks derived from topic models.



\- `03\_metrics/` — Network metric analysis including brokerage, centrality, and structural measurements.



\- `04\_topic\_modeling/` — MALLET pipelines, pyLDAvis visualizations, and topic dendrogram construction.



\- `docs/` — Methodological notes, data format specifications, and supporting documentation.



\- `workflows/` — Descriptions of how scripts were applied in specific case studies (e.g., the 2012 literature corpus and the Five Percenter Hip Hop corpus).



---



\## Data Format Assumptions



Most network scripts assume input in the form of a \*\*binary incidence matrix\*\* — a spreadsheet representing relationships between cases and features.



Typical structure:



\- Rows = cases (books, songs, etc.)

\- Columns = tropes, topics, or features

\- Presence indicated by `"X"`

\- Absence left blank



From this matrix, the scripts construct:



\- bipartite case × trope networks

\- projected one-mode trope × trope networks

\- co-occurrence matrices

\- network metrics and structural diagnostics



---



\## Installation



Python \*\*3.9+\*\* recommended.



Install dependencies with:



