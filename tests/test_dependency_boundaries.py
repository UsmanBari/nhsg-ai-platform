"""Unit tests to enforce architectural boundaries and import constraints.

Uses Python AST parser to check that checker modules do not import maker or bridge
modules, bridge modules do not import maker modules, and no circular imports exist.
"""

import ast
import os
import unittest
from typing import Dict, List, Set


class TestDependencyBoundaries(unittest.TestCase):
    """Verifies strict adherence to the Maker -> Bridge -> Checker architecture."""

    def setUp(self) -> None:
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.modules_to_inspect = []
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("test_") and file != "create_tree.py" and file != "create_agent_stubs.py":
                    self.modules_to_inspect.append(os.path.join(root, file))

    def _get_module_role(self, filepath: str) -> str:
        """Determines if a file belongs to maker, bridge, checker, or other/common."""
        normalized_path = filepath.replace("\\", "/")
        if "/agents/maker/" in normalized_path or "/pipelines/evidence_pipeline/" in normalized_path:
            return "maker"
        elif "/agents/bridge/" in normalized_path:
            return "bridge"
        elif "/agents/checker/" in normalized_path or "/pipelines/disbursement_pipeline/" in normalized_path:
            return "checker"
        return "other"

    def _get_imported_modules(self, filepath: str) -> List[str]:
        """Parses a Python file and returns a list of imported module strings."""
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_one_way_dependency_rules(self) -> None:
        """Enforces that checker/bridge do not import maker, and checker does not import bridge."""
        for filepath in self.modules_to_inspect:
            role = self._get_module_role(filepath)
            if role == "other":
                continue

            imported_modules = self._get_imported_modules(filepath)
            for imp in imported_modules:
                # Resolve relative or package imports
                # e.g., "agents.maker.evidence_collector" -> contains "maker"
                imp_lower = imp.lower()

                if role == "checker":
                    # Checker cannot import from Maker or Bridge
                    self.assertNotIn(
                        "maker",
                        imp_lower,
                        f"Boundary violation in {filepath}: Checker module imports maker module '{imp}'",
                    )
                    self.assertNotIn(
                        "bridge",
                        imp_lower,
                        f"Boundary violation in {filepath}: Checker module imports bridge module '{imp}'",
                    )
                elif role == "bridge":
                    # Bridge cannot import from Maker
                    self.assertNotIn(
                        "maker",
                        imp_lower,
                        f"Boundary violation in {filepath}: Bridge module imports maker module '{imp}'",
                    )

    def test_no_circular_dependencies(self) -> None:
        """Builds a dependency graph and checks for cycles across the codebase."""
        # Map file paths to their module names
        dep_graph: Dict[str, Set[str]] = {}
        
        # Build dependency graph
        for filepath in self.modules_to_inspect:
            # e.g., c:\path\nhsg-ai-platform\agents\maker\evidence_collector\evidence_collector.py
            # Convert to relative path from root
            rel_path = os.path.relpath(filepath, self.root_dir).replace("\\", "/")
            module_key = rel_path.replace(".py", "").replace("/__init__", "").replace("/", ".")
            
            imported = self._get_imported_modules(filepath)
            dep_graph[module_key] = set()
            for imp in imported:
                # We only care about internal imports
                # check if the import starts with known top level packages
                if (imp.startswith("agents") or imp.startswith("pipelines") or 
                        imp.startswith("state") or imp.startswith("schemas") or 
                        imp.startswith("policy")):
                    dep_graph[module_key].add(imp)

        # Cycle detection using DFS (recursive stack tracking)
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            # Find matching module or prefix in dep_graph
            # (since imports can be submodules like 'agents.maker.evidence_collector')
            neighbors = dep_graph.get(node, set())
            if not neighbors:
                # Check prefix match
                for key in dep_graph:
                    if node.startswith(key):
                        neighbors = dep_graph[key]
                        break

            for neighbor in neighbors:
                # Normalize neighbor key to match keys in dep_graph
                normalized_neighbor = neighbor
                for key in dep_graph:
                    if neighbor.startswith(key):
                        normalized_neighbor = key
                        break

                if normalized_neighbor not in visited:
                    if has_cycle(normalized_neighbor):
                        return True
                elif normalized_neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in dep_graph:
            if node not in visited:
                self.assertFalse(
                    has_cycle(node),
                    f"Circular dependency detected containing module: {node}",
                )


if __name__ == "__main__":
    unittest.main()
