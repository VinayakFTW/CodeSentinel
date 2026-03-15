"""
ingest/dep_graph.py

Builds a module-level dependency graph from FileAnalysis objects.

Graph schema
------------
Nodes: module paths (relative to repo root, e.g. "auth/models.py")
Edges: directed import relationship  A → B means "A imports B"

The graph also stores a function-call index: given a function name,
what files define it and which files call it.

Used by the hybrid retriever to expand context beyond a single matched file.
"""

import os
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from ingest.ast_parser import FileAnalysis, FunctionSymbol, ImportEdge


class DependencyGraph:
    """
    Wraps a NetworkX DiGraph and exposes retrieval helpers used by the
    HybridRetriever to expand context around matched symbols.
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        # Maps function/class name → list of files that define it
        self._definitions: Dict[str, List[str]] = defaultdict(list)
        # Maps function name → list of files that call it
        self._callers: Dict[str, List[str]] = defaultdict(list)
        # Maps file → list of functions defined in it
        self._file_symbols: Dict[str, List[str]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Building the graph
    # ------------------------------------------------------------------

    def build(self, analyses: List[FileAnalysis], repo_root: str = "") -> None:
        """
        Populate graph from a list of FileAnalysis objects.
        Call this once after parsing the whole repository.
        """
        print("[DepGraph] Building dependency graph...")

        for analysis in analyses:
            if analysis.parse_error:
                continue

            src = self._normalise(analysis.path, repo_root)
            self.graph.add_node(src)

            # Register defined symbols
            for fn in analysis.functions:
                self._definitions[fn.name].append(src)
                self._definitions[fn.qualified_name].append(src)
                self._file_symbols[src].append(fn.name)

                # Register call edges (caller file → callee name)
                for callee in fn.calls:
                    self._callers[callee].append(src)

            for cls in analysis.classes:
                self._definitions[cls.name].append(src)

            # Register import edges
            for imp in analysis.imports:
                # Try to resolve the import to a file in the repo
                resolved = self._resolve_import(imp.imported_module, repo_root)
                if resolved and resolved != src:
                    # GraphML only supports primitive types — serialize list to string
                    self.graph.add_edge(src, resolved, names=",".join(imp.imported_names))

        print(
            f"[DepGraph] Graph built: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges, "
            f"{len(self._definitions)} symbols indexed."
        )

    # ------------------------------------------------------------------
    # Context expansion helpers (used by HybridRetriever)
    # ------------------------------------------------------------------

    def get_dependencies(self, filepath: str, hops: int = 1) -> Set[str]:
        """
        Files that `filepath` imports, up to `hops` levels deep.
        (files this file depends ON)
        """
        return self._bfs_neighbors(filepath, direction="successors", hops=hops)

    def get_dependents(self, filepath: str, hops: int = 1) -> Set[str]:
        """
        Files that import `filepath`.
        (files that depend ON this file)
        """
        return self._bfs_neighbors(filepath, direction="predecessors", hops=hops)

    def get_callers_of(self, symbol_name: str) -> List[str]:
        """Return files that call `symbol_name`."""
        return list(set(self._callers.get(symbol_name, [])))

    def get_definers_of(self, symbol_name: str) -> List[str]:
        """Return files that define `symbol_name`."""
        return list(set(self._definitions.get(symbol_name, [])))

    def _get_node(self, node_path: str) -> Optional[str]:
        """Safely resolve an absolute or relative path to a graph node."""
        if node_path in self.graph.nodes:
            return node_path
        
        # Normalize slashes for safe cross-platform comparison
        norm_path = node_path.replace('\\', '/')
        
        for n in self.graph.nodes:
            if norm_path.endswith(n.replace('\\', '/')):
                return n
        return None

    def get_file_symbols(self, filepath: str) -> List[str]:
        """Return names of all functions/classes defined in `filepath`."""
        actual_node = self._get_node(filepath)
        if actual_node and actual_node in self._file_symbols:
            return self._file_symbols[actual_node]
        return []
        
    def expand_context(
        self,
        seed_files: List[str],
        dep_hops: int = 1,
        max_files: int = 15,
    ) -> List[str]:
        """
        Given a list of seed files (from vector search hits), expand to include
        their direct dependencies and dependents. Returns a deduplicated,
        size-capped list of files for the LLM context window.
        """
        expanded: Set[str] = set(seed_files)
        for f in seed_files:
            expanded |= self.get_dependencies(f, hops=dep_hops)
            expanded |= self.get_dependents(f, hops=dep_hops)

        # Rank: seed files first, then expanded
        ordered = list(seed_files)
        for f in expanded:
            if f not in ordered:
                ordered.append(f)
        return ordered[:max_files]

    def shortest_path(self, source: str, target: str) -> Optional[List[str]]:
        """Return import chain from source to target, if one exists."""
        try:
            return nx.shortest_path(self.graph, source, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_strongly_connected(self) -> List[List[str]]:
        """Return groups of files that form circular import cycles."""
        cycles = [
            list(c)
            for c in nx.strongly_connected_components(self.graph)
            if len(c) > 1
        ]
        return cycles

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist graph to a GraphML file."""
        nx.write_graphml(self.graph, path)
        print(f"[DepGraph] Saved graph to '{path}'.")

    def load(self, path: str) -> None:
        """Load a previously saved graph."""
        self.graph = nx.read_graphml(path)
        print(f"[DepGraph] Loaded graph from '{path}'.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bfs_neighbors(self, node: str, direction: str, hops: int) -> Set[str]:
        actual_node = self._get_node(node)
        if not actual_node:
            return set()
            
        visited: Set[str] = set()
        frontier = {actual_node}
        for _ in range(hops):
            next_frontier: Set[str] = set()
            for n in frontier:
                if direction == "successors":
                    neighbours = set(self.graph.successors(n))
                else:
                    neighbours = set(self.graph.predecessors(n))
                next_frontier |= neighbours - visited - {actual_node}
            visited |= next_frontier
            frontier = next_frontier
        return visited

    @staticmethod
    def _normalise(filepath: str, repo_root: str) -> str:
        """Make filepath relative to repo root for stable node IDs."""
        if repo_root:
            try:
                return os.path.relpath(filepath, repo_root)
            except ValueError:
                pass
        return filepath

    @staticmethod
    def _resolve_import(module_name: str, repo_root: str) -> Optional[str]:
        """
        Try to map a dotted module name to a .py file within the repo.
        Returns None for third-party packages we can't resolve locally.
        """
        if not repo_root or not module_name:
            return None
        # Convert "auth.models" → "auth/models.py"
        candidate = module_name.replace(".", os.sep) + ".py"
        full = os.path.join(repo_root, candidate)
        if os.path.exists(full):
            return candidate
        # Try as a package __init__.py
        pkg = module_name.replace(".", os.sep)
        init = os.path.join(repo_root, pkg, "__init__.py")
        if os.path.exists(init):
            return os.path.join(pkg, "__init__.py")
        return None