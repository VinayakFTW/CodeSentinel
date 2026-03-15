"""
ingest/embedder.py

Embeds code at function/class granularity rather than arbitrary text chunks.

Why this matters
----------------
The old approach split files by character count (chunk_size=1000). A function
could be split mid-body, losing context. A docstring could land in a different
chunk than its implementation.

This embedder creates one embedding unit per symbol:
    [signature] + [docstring] + [source body]

Each chunk is a semantically complete unit. Retrieval therefore returns whole
functions rather than orphaned fragments.
"""

import os
from pathlib import Path
from typing import List
import sys

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

from ingest.ast_parser import FileAnalysis

load_dotenv()

# ---------------------------------------------------------------------------
# Offline Model Path Resolution
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # The directory where the .exe is located (e.g., dist/)
    exe_dir = os.path.dirname(sys.executable)
    
    # 1. PyInstaller 5.3+ puts bundled data in the _internal folder
    internal_path = os.path.join(exe_dir, "_internal", "offline_model")
    
    # 2. Older PyInstaller versions or manual placement next to the .exe
    primary_path = os.path.join(exe_dir, "offline_model")
    
    # 3. Fallback for testing from within the dist folder before moving
    fallback_path = os.path.join(os.path.dirname(exe_dir), "offline_model")
    
    if os.path.exists(internal_path):
        OFFLINE_MODEL_PATH = internal_path
    elif os.path.exists(primary_path):
        OFFLINE_MODEL_PATH = primary_path
    elif os.path.exists(fallback_path):
        OFFLINE_MODEL_PATH = fallback_path
    else:
        OFFLINE_MODEL_PATH = internal_path # Default fallback
else:
    # Running as a normal Python script
    bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OFFLINE_MODEL_PATH = os.path.join(bundle_dir, "offline_model")

if os.path.exists(OFFLINE_MODEL_PATH):
    EMBEDDING_MODEL_NAME = OFFLINE_MODEL_PATH
    print(f"[Embedder] Using local offline model: {EMBEDDING_MODEL_NAME}")
else:
    EMBEDDING_MODEL_NAME = "jinaai/jina-code-embeddings-1.5b"
    print(f"[Embedder] Local model not found, falling back to HuggingFace: {EMBEDDING_MODEL_NAME}")

PERSIST_DIRECTORY = os.environ.get("PERSIST_DIRECTORY", "chroma_db")
COLLECTION_NAME = "codebase_symbols"


def _make_documents(analyses: List[FileAnalysis]) -> List[Document]:
    """
    Convert parsed FileAnalysis objects into LangChain Documents.

    Each document represents one function or one class.
    Metadata is rich enough for the retriever to reconstruct location info.
    """
    docs: List[Document] = []

    for analysis in analyses:
        if analysis.parse_error:
            continue

        for fn in analysis.functions:
            # Embed: signature + docstring + source body
            # The signature appears first so the embedding captures
            # the function's type contract prominently.
            text_parts = [fn.signature]
            if fn.docstring:
                text_parts.append(f'"""{fn.docstring}"""')
            text_parts.append(fn.source)
            text = "\n".join(text_parts)

            docs.append(Document(
                page_content=text,
                metadata={
                    "kind": "function",
                    "name": fn.name,
                    "qualified_name": fn.qualified_name,
                    "source": fn.file,
                    "line_start": fn.line_start,
                    "line_end": fn.line_end,
                    "class_name": fn.class_name or "",
                    "is_method": str(fn.is_method),
                    "signature": fn.signature,
                    "has_docstring": str(bool(fn.docstring)),
                },
            ))

        for cls in analysis.classes:
            text_parts = [f"class {cls.name}({', '.join(cls.bases)}):"]
            if cls.docstring:
                text_parts.append(f'    """{cls.docstring}"""')
            text_parts.append(cls.source)
            text = "\n".join(text_parts)

            docs.append(Document(
                page_content=text,
                metadata={
                    "kind": "class",
                    "name": cls.name,
                    "qualified_name": cls.name,
                    "source": cls.file,
                    "line_start": cls.line_start,
                    "line_end": cls.line_end,
                    "class_name": cls.name,
                    "bases": ", ".join(cls.bases),
                    "signature": f"class {cls.name}",
                    "has_docstring": str(bool(cls.docstring)),
                },
            ))

    return docs


def build_vector_store(
    analyses: List[FileAnalysis],
    persist_dir: str = PERSIST_DIRECTORY,
) -> Chroma:
    """
    Build (or rebuild) the ChromaDB vector store from parsed FileAnalysis objects.
    Replaces the old ingest.py logic with function-level embeddings.
    """
    docs = _make_documents(analyses)
    print(f"[Embedder] Embedding {len(docs)} symbol documents...")

    embedding_fn = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": "cuda", "trust_remote_code": True},
    )

    # Batch to avoid OOM on large repos
    BATCH = 1
    db = None
    for i in range(0, len(docs), BATCH):
        batch = docs[i : i + BATCH]
        if db is None:
            db = Chroma.from_documents(
                documents=batch,
                embedding=embedding_fn,
                persist_directory=persist_dir,
                collection_name=COLLECTION_NAME,
            )
        else:
            db.add_documents(batch)
        print(f"  [Embedder] {min(i + BATCH, len(docs))}/{len(docs)} embedded...")

    print(f"[Embedder] Vector store saved to '{persist_dir}'.")
    return db


def load_vector_store(persist_dir: str = PERSIST_DIRECTORY) -> Chroma:
    """Load an existing vector store (no re-embedding)."""
    embedding_fn = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={"device": "cuda", "trust_remote_code": True},
    )
    return Chroma(
        persist_directory=persist_dir,
        embedding_function=embedding_fn,
        collection_name=COLLECTION_NAME,
    )
