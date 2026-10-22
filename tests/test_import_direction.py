"""The import-direction rule (ARCHITECTURE.md 3) enforced as a test.

The dependency graph is not a style preference. Two things depend on it:

*   ``extract/verify.py`` and ``corpus/prefilter.py`` must stay **pure** — they
    import nothing from the project except ``errors.py``. That is what makes the
    verifier testable without a model, and therefore trustworthy.
*   ``vector/`` must not import ``storage/``. That import is what would let a
    device name reach the cloud, so its absence is the *enforcement* of the
    privacy boundary (RULES.md 3.1a).

The graph is read from the source tree with ``ast``, so it cannot drift from
the code the way a written rule in a comment does.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
PACKAGE = "sloth_drawer"

#: Modules that may only ever touch ``errors`` from the project.
PURE_MODULES = {
    "sloth_drawer.extract.verify",
    "sloth_drawer.corpus.prefilter",
}

#: Package-level restrictions. A module in the key may import the project
#: modules listed in the value (a value also permits its submodules).
PACKAGE_RULES: dict[str, set[str]] = {
    "sloth_drawer.vector": {
        "sloth_drawer.errors",
        "sloth_drawer.retrieval.base",
        "sloth_drawer.extract.embed",
    },
    "sloth_drawer.web": {
        "sloth_drawer.errors",
        "sloth_drawer.storage",
        "sloth_drawer.render",
    },
}

#: Third-party packages that must never appear in the source tree (RULES.md 4.1).
BANNED_PACKAGES = {
    "openai",
    "anthropic",
    "google",
    "groq",
    "mistralai",
    "cohere",
    "torch",
    "transformers",
    "accelerate",
    "peft",
    "langchain",
    "langchain_core",
    "langchain_community",
    "langgraph",
    "llama_index",
    "crewai",
    "autogen",
    "smolagents",
    "pydantic_ai",
    "chromadb",
    "weaviate",
    "pinecone",
    "faiss",
    "rank_bm25",
    "whoosh",
    "elasticsearch",
    "tiktoken",
    "tenacity",
    "rich",
    "textual",
    "tqdm",
    "dotenv",
    "sqlalchemy",
    "psycopg2",
    "asyncpg",
    "requests",
    "httpx",
    "ollama",
    "pdfplumber",
    "fitz",
    "pymupdf",
}


def _module_name(path: Path) -> str:
    """``src/sloth_drawer/corpus/prefilter.py`` -> ``sloth_drawer.corpus.prefilter``."""
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(path: Path) -> str:
    """The package a module's relative imports resolve against."""
    module = _module_name(path)
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _resolve_relative(package: str, level: int, name: str | None) -> str:
    """Resolve ``from . import x`` / ``from ..errors import y`` to a dotted name."""
    parts = package.split(".") if package else []
    if level > 1:
        parts = parts[: len(parts) - (level - 1)]
    if name:
        parts = [*parts, *name.split(".")]
    return ".".join(parts)


def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _module_names() -> set[str]:
    return {_module_name(path) for path in _source_files()}


def _project_imports(path: Path, known: set[str]) -> set[str]:
    """Every project-internal module this file imports.

    ``from errors import ConfigError`` names a symbol, not a module, so the
    symbol is only kept when it really is a module in the tree.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path)
    found: set[str] = set()

    def keep(candidate: str) -> None:
        if candidate in known:
            found.add(candidate)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                keep(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                resolved = _resolve_relative(package, node.level, node.module)
                keep(resolved)
                for alias in node.names:
                    keep(f"{resolved}.{alias.name}")
            elif node.module:
                keep(node.module)
                for alias in node.names:
                    keep(f"{node.module}.{alias.name}")
    return found


def _third_party_imports(path: Path) -> set[str]:
    """Every third-party top-level package this file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module == PACKAGE or node.module.startswith(f"{PACKAGE}."):
                continue
            found.add(node.module.split(".")[0])
    return found


SOURCE_FILES = _source_files()
KNOWN_MODULES = _module_names()


def test_the_source_tree_exists() -> None:
    assert SOURCE_FILES, "no source files found — the package layout is wrong"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_no_banned_third_party_imports(path: Path) -> None:
    offenders = _third_party_imports(path) & BANNED_PACKAGES
    assert not offenders, f"{path.name} imports banned package(s): {sorted(offenders)}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_pure_modules_import_only_errors(path: Path) -> None:
    module = _module_name(path)
    if module not in PURE_MODULES:
        return
    imports = _project_imports(path, KNOWN_MODULES)
    offenders = {name for name in imports if name != "sloth_drawer.errors"}
    assert not offenders, f"{module} must stay pure, but imports {sorted(offenders)}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_package_rules_are_respected(path: Path) -> None:
    module = _module_name(path)
    for prefix, allowed in PACKAGE_RULES.items():
        if not (module == prefix or module.startswith(f"{prefix}.")):
            continue
        for imported in _project_imports(path, KNOWN_MODULES):
            permitted = any(
                imported == entry or imported.startswith(f"{entry}.") for entry in allowed
            )
            assert permitted, (
                f"{module} imports {imported}, which is outside its allowed set {sorted(allowed)}"
            )


def test_the_import_graph_is_acyclic() -> None:
    """A cycle would make the layering meaningless."""
    graph: dict[str, set[str]] = {
        _module_name(path): _project_imports(path, KNOWN_MODULES) for path in SOURCE_FILES
    }
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        marker = state.get(node)
        if marker == 2:
            return
        if marker == 1:
            cycle = " -> ".join([*stack[stack.index(node) :], node])
            pytest.fail(f"import cycle: {cycle}")
        state[node] = 1
        for neighbour in graph.get(node, ()):
            visit(neighbour, [*stack, node])
        state[node] = 2

    for node in graph:
        visit(node, [])
