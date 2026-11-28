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

## Running

Notebooks assume the `synirmos` package is installed (this repo, editable)
and only use the standard library plus the library itself unless the
notebook header says otherwise. With Jupyter available:

```bash
uv run --with jupyter jupyter lab examples/onto_kg/notebooks/
```

Every notebook is also executable as a plain script: concatenate its code
cells in order and run with `uv run python`.
