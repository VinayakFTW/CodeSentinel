<div align="center">

# 🛡️ Code-Sentinel v2

### Fully local, multi-agent AI code intelligence — no cloud, no API keys, zero data leaves your machine.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=flat&logo=ollama&logoColor=white)](https://ollama.ai)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-FF6B35?style=flat)](https://www.trychroma.com)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=flat)](LICENSE)

</div>

---

## ✨ What It Does

Point Code-Sentinel at any Python repo. It indexes every function and class, then gives you three superpowers:

| Mode | What you get |
|------|-------------|
| 💬 **Q&A** | Ask plain-English questions → get cited answers with `file.py:line` references |
| 🔍 **Review** | 10 specialist AI agents audit your code in parallel → one ranked report |
| 📝 **Docs** | Auto-generate docstrings + module summaries, incrementally on every git push |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGEST  (one-time)                       │
│                                                                 │
│   .py files → AST Parser → ┬→ SQLite Symbol Index              │
│                             ├→ NetworkX Dep Graph (.graphml)    │
│                             └→ ChromaDB Vector Store            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     HYBRID RETRIEVER                            │
│                                                                 │
│   Query → Vector Search (top-k) → Dep-Graph Expansion          │
│            (semantic match)        (import neighbours)         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────┬───────┴────────┬───────────────┐
        ▼             ▼                ▼               ▼
    Q&A Pipeline  Review Pipeline  Docs Pipeline  Re-index
    (14B model)   (10x 0.5b +      (14B model)
                   1x 14B synth)
```

### Two-model tier

| Model | Role | VRAM |
|-------|------|------|
| `qwen2.5-coder:0.5b` | 10 parallel worker agents | ~500 MB |
| `qwen2.5-coder:14b` | Planning, synthesis, Q&A, docs | ~8–10 GB |

> Workers run first, then are **explicitly evicted** (`keep_alive=0`) before the 14B model loads. This lets the whole system run on a single consumer GPU.

---

## 📁 Project Structure

```
CodeSentinel-main/
└── agent-python/
    ├── cli.py                  ← Start here (handles setup + repo selection)
    ├── main.py                 ← Core CLI menu (Q&A / Review / Docs / Re-index)
    ├── setup.py                ← Auto-installs Ollama, pulls models, sets env vars
    ├── download_model.py       ← Pre-downloads embedding model for offline use
    ├── build.sh                ← PyInstaller → self-contained binary
    │
    ├── core/
    │   ├── paths.py            ← PyInstaller-safe path resolution (sys.executable)
    │   ├── model_manager.py    ← Ollama health check + VRAM eviction
    │   ├── worker.py           ← WorkerAgent: 10 specialisations, iterative search
    │   └── orchestrator.py     ← OrchestratorAgent (legacy; superseded by ReviewPipeline)
    │
    ├── ingest/
    │   ├── ast_parser.py       ← AST parse + 9 deterministic static-analysis rules
    │   ├── dep_graph.py        ← NetworkX DiGraph: import edges + BFS expansion
    │   ├── embedder.py         ← Symbol-granularity ChromaDB embeddings
    │   ├── symbol_index.py     ← SQLite: exact/prefix symbol lookup
    │   └── run_ingest.py       ← Orchestrates all 4 ingest steps
    │
    ├── pipelines/
    │   ├── qa.py               ← Retrieve → format → 14B answer
    │   ├── review.py           ← Static + 10 workers + 14B synthesis
    │   └── docs.py             ← Git-diff-aware incremental documentation
    │
    ├── retrieval/
    │   └── hybrid_retriever.py ← Vector search + dep-graph expansion combined
    │
    └── docs/                   ← Auto-generated output (Code-Sentinel on itself)
        ├── .summary_cache.json
        ├── architecture.md
        └── *.md
```

---

## ⚙️ How the Review Works

```
Review Pipeline — 3 Phases
══════════════════════════════════════════════════════════

Phase 1 │ Static Analysis (no LLM, instant)
────────┤ Re-parses all .py files with ast_parser
        │ 9 deterministic rules fire: bare-except, mutable-default,
        │ hardcoded-secret, sql-fstring, eval-exec, os-system, ...
        │
Phase 2 │ 10 Parallel Semantic Workers (qwen2.5-coder:0.5b)
────────┤ Each worker owns ONE specialisation domain:
        │   security · logic bugs · performance · error-handling
        │   maintainability · API design · data validation
        │   concurrency · import hygiene · type annotations
        │
        │ Per worker loop (up to 3 rounds):
        │   generate_queries → retrieve (vector + dep-expand)
        │   → analyse snippets → parse ISSUE_START/END blocks
        │   → refine queries from finding keywords → next round
        │
Phase 3 │ 14B Synthesis
────────┤ unload_workers() → reload qwen2.5-coder:14b
        │ All findings (static + semantic) → _SYNTHESIS_PROMPT
        │ Output: review.md (ranked by severity) + documentation.md

══════════════════════════════════════════════════════════
```

---

## 🔍 How Retrieval Works

Every search is **two-stage**:

```
1. Vector Search
   User query → ChromaDB similarity_search → top-k symbols
   (each symbol = complete function/class, never a broken chunk)

2. Dependency Graph Expansion
   Matched files → BFS 1 hop on import graph
   → add symbols from imported files + files that import them
   → LLM sees the full cross-module picture
```

**Why not plain chunking?** A standard 1000-char splitter cuts function bodies in half. Code-Sentinel embeds one `Document` per complete symbol: `signature + docstring + source body`. Every retrieval hit is parseable.

---

## 🚀 Installation

### Prerequisites

- Python **≥ 3.10**
- [Ollama](https://ollama.ai) installed and running
- GPU with **≥ 16 GB VRAM** recommended (CPU works, but slowly)
- ~12 GB disk space (models + indexes)

### Steps

```bash
# 1. Clone
git clone https://github.com/your-org/CodeSentinel.git
cd CodeSentinel-main/agent-python

# 2. Virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Pull models (Ollama must be running)
ollama pull qwen2.5-coder:0.5b
ollama pull qwen2.5-coder:14b    # ~8 GB

# 5. (Recommended) Download embedding model for offline use
python download_model.py         # saves to ./offline_model/
```

---

## ▶️ Running

```bash
# Recommended: guided setup + repo selection
python cli.py

# Or: direct launch if .env is already configured
python main.py
```

`cli.py` will:
1. Check Ollama is running (auto-install if needed)
2. Pull required models if missing
3. Ask for your repo path
4. Run ingestion (or skip if indexes exist)
5. Drop you into the main menu

---

## 🖥️ CLI Menu

```
=======================================
|  [1] Q&A        Ask about the code  |
|  [2] Review     Full codebase audit |
|  [3] Docs       Update documentation|
|  [4] Re-index   Re-run ingest       |
|  [q] Quit                           |
=======================================
```

**Q&A example:**
```
Question: How does the authentication middleware work?

[Q&A] Using 17 symbol(s) as context.

The middleware is implemented in middleware/auth.py:34. The
`require_auth` decorator (line 34–67) validates the JWT token
via `TokenValidator.verify()` (jwt_utils.py:12)...
```

**Review output** → `review.md`:
```markdown
## Critical Issues (HIGH severity)
- [hardcoded-secret] config.py:14 — API key assigned as string literal
- [sql-fstring] db/queries.py:89 — f-string SQL query, possible injection

## Warnings (MEDIUM severity)
- [bare-except] handlers/upload.py:43 — catches all exceptions silently
...
```

---

## ⚙️ Configuration

All paths are set automatically by `cli.py` and persisted to `.env`.
Override any of them manually:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCE_DIR` | *(required)* | Absolute path to repo being analysed |
| `DATA_DIR` | `{app_dir}/data` | Parent dir for all index files |
| `PERSIST_DIRECTORY` | `{DATA_DIR}/chroma_db` | ChromaDB vector store |
| `SYMBOL_DB_PATH` | `{DATA_DIR}/symbol_index.db` | SQLite symbol index |
| `DEP_GRAPH_PATH` | `{DATA_DIR}/dep_graph.graphml` | NetworkX dep graph |
| `DOCS_DIR` | `{SOURCE_DIR}/docs` | Documentation output |
| `EMBEDDING_MODEL_NAME` | `jinaai/jina-code-embeddings-1.5b` | HuggingFace fallback |

---

## 📦 Building a Standalone Binary

```bash
# First, download the embedding model
python download_model.py

# Then build (from repo root)
chmod +x build.sh && ./build.sh
# → dist/CodeSentinel/CodeSentinel  (Linux/macOS)
# → dist/CodeSentinel/CodeSentinel.exe  (Windows)
```

> **Linux/macOS users:** change the `--add-data` separator in `build.sh` from `;` to `:` before building.

---

## 🔧 Extending Code-Sentinel

**Add a new review specialisation** — edit `core/worker.py`:
```python
SPECIALIZATIONS = [
    ...
    "async/await correctness (unawaited coroutines, blocking calls in async context)",
]
```

**Add a new static analysis rule** — add a visitor to `StaticAnalyser` in `ingest/ast_parser.py`:
```python
def visit_Delete(self, node: ast.Delete):
    for target in node.targets:
        if isinstance(target, ast.Subscript):
            self._emit(node.lineno, "LOW", "del-subscript",
                "`del dict[key]` may raise KeyError.",
                "Use `dict.pop(key, None)` instead.")
    self.generic_visit(node)
```

**Change models** — edit `core/model_manager.py`:
```python
WORKER_MODEL       = "qwen2.5-coder:1.5b"
ORCHESTRATOR_MODEL = "qwen2.5-coder:32b"
```

---

## ⚠️ Known Issues

| # | Location | Issue |
|---|----------|-------|
| 1 | `pipelines/review.py` | `_save` is decorated `@staticmethod` but takes `self` — will raise `AttributeError` at runtime. **Fix:** remove `@staticmethod`. |
| 2 | `ingest/dep_graph.py` | `_definitions`, `_callers`, `_file_symbols` are not persisted to GraphML. After `load()`, `get_callers_of()` always returns `[]`. |
| 3 | `build.sh` | `--add-data "offline_model;offline_model"` uses Windows `;` separator. Use `:` on Linux/macOS. |
| 4 | `core/model_manager.py` | `OLLAMA_BASE_URL` is hardcoded to `localhost`. No env var override for remote Ollama. |
| 5 | `ingest/embedder.py` | `device="cuda"` is hardcoded. Crashes if no CUDA GPU present. |

---

## 🗺️ Roadmap

- [ ] Fix `ReviewPipeline._save` staticmethod bug
- [ ] Persist dep-graph symbol maps (JSON sidecar alongside GraphML)
- [ ] `OLLAMA_BASE_URL` env var for remote Ollama support
- [ ] CUDA device auto-detection with CPU fallback
- [ ] Non-Python language support via `tree-sitter`
- [ ] Numeric code health score per file
- [ ] REST API (`fastapi` already in requirements)
- [ ] Review diff mode (new vs resolved issues across runs)

---

## 📄 Generated Output Example

After running `[3] Docs` on this repo itself — see [`agent-python/docs/`](agent-python/docs/):

```
docs/
├── architecture.md       ← High-level system overview
├── ast_parser.md         ← Per-module: classes, functions, static warnings
├── hybrid_retriever.md
├── worker.md
└── ...
```

---

<div align="center">

**Built to run entirely on your hardware. Your code never leaves your machine.**

</div>
