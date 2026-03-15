"""
main.py — Code-Sentinel entry point.
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

from core.model_manager import check_ollama_running, warmup_model, ORCHESTRATOR_MODEL
from ingest.dep_graph import DependencyGraph
from ingest.symbol_index import SymbolIndex
from ingest.embedder import load_vector_store
from retrieval.hybrid_retriever import HybridRetriever
from pipelines.qa import QAPipeline
from pipelines.review import ReviewPipeline
from pipelines.docs import DocsPipeline

SOURCE_DIR  = os.environ.get("SOURCE_DIR")
GRAPH_PATH  = os.environ.get("DEP_GRAPH_PATH")
SYMBOL_DB   = os.environ.get("SYMBOL_DB_PATH")
VECTOR_DIR  = os.environ.get("PERSIST_DIRECTORY")
DOCS_DIR    = os.environ.get("DOCS_DIR")

BANNER = """
========================================================
|              Code-Sentinel  v2  (Hybrid)             |
|  AST + DepGraph + SymbolIndex + Vector + 10 Workers  |
========================================================
"""


def load_shared_resources():
    print("[Init] Loading vector store...")
    vector_store = load_vector_store(VECTOR_DIR)

    print("[Init] Loading dependency graph...")
    dep_graph = DependencyGraph()
    if os.path.exists(GRAPH_PATH):
        dep_graph.load(GRAPH_PATH)
    else:
        print(f"  WARNING: No dep graph at '{GRAPH_PATH}'. Run re-index first.")

    print("[Init] Loading symbol index...")
    symbol_index = SymbolIndex(db_path=SYMBOL_DB)
    print(f"  Symbols: {symbol_index.stats()}")

    retriever = HybridRetriever(
        vector_store=vector_store,
        dep_graph=dep_graph,
        symbol_index=symbol_index,
        vector_k=8,
        dep_hops=1,
        max_total=20,
    )
    print("[Init] Hybrid retriever ready.\n")
    return retriever


def main():
    print(BANNER)

    if not check_ollama_running():
        print("ERROR: Ollama is not running. Start with: ollama serve")
        sys.exit(1)

    if not os.path.exists(VECTOR_DIR):
        print(f"ERROR: No vector store. Run:\n  python -m ingest.run_ingest --source {SOURCE_DIR}")
        sys.exit(1)

    retriever = load_shared_resources()

    qa_pipeline     = QAPipeline(retriever)
    review_pipeline = ReviewPipeline(
        retriever=retriever, symbol_index=retriever.si, source_dir=SOURCE_DIR)
    docs_pipeline   = DocsPipeline(
        retriever=retriever, source_dir=SOURCE_DIR, docs_dir=DOCS_DIR)

    # warmup_model(ORCHESTRATOR_MODEL, keep_alive_seconds=1800)

    while True:
        print("=======================================")
        print("|  [1] Q&A        Ask about the code  |")
        print("|  [2] Review     Full codebase audit |")
        print("|  [3] Docs       Update documentation|")
        print("|  [4] Re-index   Re-run ingest       |")
        print("|  [q] Quit                           |")
        print("=======================================")

        try:
            choice = input("Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice in ("q", "quit", "exit"):
            break
        elif choice == "1":
            qa_pipeline.interactive_loop()
        elif choice == "2":
            scope = input("Scope (Enter = full audit): ").strip() or "Full codebase audit"
            review_pipeline.run(user_request=scope)
        elif choice == "3":
            mode = input("Full [f] or incremental [i]? ").strip().lower()
            if mode == "f":
                docs_pipeline.run_full()
            else:
                since = input("Since ref (default HEAD~1): ").strip() or "HEAD~1"
                docs_pipeline.run_incremental(since=since)
        elif choice == "4":
            src = input(f"Source dir (default {SOURCE_DIR}): ").strip() or SOURCE_DIR
            from ingest.run_ingest import run_ingest
            run_ingest(src, clean=True)
            retriever = load_shared_resources()
            qa_pipeline.retriever = retriever
            review_pipeline.retriever = retriever
            docs_pipeline.retriever = retriever
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()
