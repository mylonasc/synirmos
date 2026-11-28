# ONTO-KG worked example: ontology-driven KG over documents

Consumer-style demonstration of `docs/epics/EPIC_ONTO_KG.md`, tracked in
parent issue #1 (slices #2–#8). Each slice adds one narrative notebook
under `notebooks/`:

| Notebook | Slice | Content |
| --- | --- | --- |
| `00_ontology_registry.ipynb` | 0 (#2) | Metamodel, registry evolution, validation, releases |
| `01_ontology_in_graph.ipynb` | 1 (#3) | Persisting the ontology in GestaltDB, schema compiler |
| `02_lexical_chunks.ipynb` | 2 (#4) | Chunk layer, co-located embeddings, index port |
| `03_guided_extraction.ipynb` | 3 (#5) | Ontology-guided JERE extraction + staging |
| `04_resolution.ipynb` | 4 (#6) | Entity resolution + idempotent writer |
| `05_dynamic_retrieval.ipynb` | 5 (#7) | Data-driven retrieval demo |

Only notebook 00 and the D0 checkpoint below currently exist; the other rows are
planned slice artifacts, not shipped examples. Notebook 00 demonstrates the
scaffold, not all of #2's remaining artifact/merge acceptance.

## Architectural prerequisites

`notebooks/D0_contracts.ipynb` accompanies the **first increment** of D0/#11:
qualified document/revision identity, content sharing versus collection/access
identity, original UTF-8/CRLF byte spans, source validity versus observed/justified
knowledge time, chunk content versus occurrences, and bounded source pages.
It is not capture/parsing implementation or completion of D0. See
`docs/DOCUMENT_CONTRACTS.md` and `docs/epics/EPIC_DECOUPLING.md` for remaining scope.

## Running

Notebooks assume the `synirmos` package is installed (this repo, editable)
and only use the standard library plus the library itself unless the
notebook header says otherwise. With Jupyter available:

```bash
uv run --with jupyter jupyter lab examples/onto_kg/notebooks/
```

Every notebook is also executable as a plain script: concatenate its code
cells in order and run with `uv run python`.

The automated offline path requires no Jupyter extra and runs existing notebook
code cells in order in fresh processes, including in the full quality gate:

```bash
uv run pytest examples/onto_kg/tests -q
```
