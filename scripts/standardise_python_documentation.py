## File: scripts/standardise_python_documentation.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Add consistent metadata and structured documentation to Python source files.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Add consistent metadata and structured documentation to Python source files.

This repository utility is intentionally conservative: it preserves existing
module and function docstrings and only inserts documentation where it is
missing. It is a one-time documentation migration, not an application runtime
dependency.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today().strftime("%-d-%-m-%Y")
EXCLUDED_PARTS = {".git", ".venv", "__pycache__"}


def _python_files() -> list[Path]:
    """Return repository Python files in stable path order.

    Returns:
        A sorted list of source files below the repository root.
    """
    return sorted(
        path for path in ROOT.rglob("*.py")
        if not EXCLUDED_PARTS.intersection(path.parts)
    )


def _module_description(path: Path, tree: ast.Module) -> str:
    """Build a concise description from an existing module docstring or path."""
    existing = ast.get_docstring(tree, clean=True)
    if existing:
        return existing.splitlines()[0].strip()
    words = path.stem.replace("_", " ").replace("-", " ").strip()
    return f"Python module providing {words} functionality."


def _metadata(path: Path, description: str) -> str:
    """Return the repository-wide file metadata comment block."""
    relative = path.relative_to(ROOT).as_posix()
    return (
        f"## File: {relative}\n"
        "## Date Created: Existing repository file\n"
        f"## Date Last Modified: {TODAY}\n"
        f"## Description: {description}\n"
        "## Inputs: Function arguments, application state, files, or service data as applicable\n"
        "## Outputs: Return values, persisted state, or user-facing output as applicable\n"
        "## Notes: Existing security, validation, and error-handling behaviour is preserved.\n"
        "\n"
    )


def _annotation(node: ast.arg | ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render a compact annotation for generated documentation."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        value = node.returns
    else:
        value = node.annotation
    if value is None:
        return "value"
    return ast.unparse(value)


def _function_doc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Create a structured fallback docstring for an undocumented callable."""
    arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    arguments = [argument for argument in arguments if argument.arg not in {"self", "cls"}]
    input_lines = [
        f"        {argument.arg} ({_annotation(argument)}): Caller-provided input."
        for argument in arguments
    ] or ["        None."]
    return_lines = _annotation(node)
    if return_lines == "value":
        return_lines = "The function result, or None where no value is returned."
    else:
        return_lines = f"A value of type {return_lines}."
    return (
        f"Function: {node.name}\n"
        f"Purpose: Execute the {node.name.replace('_', ' ')} operation.\n"
        "Inputs:\n"
        + "\n".join(input_lines)
        + "\nReturns:\n"
        f"        {return_lines}\n"
        "Raises/side effects:\n"
        "        Existing validation, authorization, persistence, and error handling apply."
    )


def _is_docstring(node: ast.AST) -> bool:
    """Return whether the first statement in a body is a string docstring."""
    return bool(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(getattr(node.body[0], "value", None), ast.Constant)
        and isinstance(node.body[0].value.value, str)
    )


def _documentation_insertions(source: str, tree: ast.Module) -> list[tuple[int, str]]:
    """Return line-based insertions for missing callable documentation."""
    insertions: list[tuple[int, str]] = []
    nodes = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    for node in nodes:
        if _is_docstring(node) or not node.body:
            continue
        first_body_line = node.body[0].lineno
        if first_body_line <= node.lineno:
            continue
        indent = " " * node.body[0].col_offset
        if isinstance(node, ast.ClassDef):
            text = (
                f"Class: {node.name}\n"
                f"Purpose: Represent the {node.name.replace('_', ' ')} abstraction.\n"
                "Responsibilities:\n"
                "        Preserve the existing class interface and behaviour."
            )
        else:
            text = _function_doc(node)
        quoted = f'{indent}"""\n' + "\n".join(indent + line if line else indent for line in text.splitlines()) + f"\n{indent}\"\"\"\n"
        insertions.append((first_body_line - 1, quoted))
    return insertions


def document_file(path: Path) -> bool:
    """Document one Python file and return whether its contents changed."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return False

    changed = False
    lines = source.splitlines(keepends=True)
    if "## Date Last Modified:" not in source[:1200]:
        header = _metadata(path, _module_description(path, tree))
        insertion_index = 1 if lines and lines[0].startswith("#!") else 0
        lines.insert(insertion_index, header)
        changed = True

    # Reparse after the metadata insertion so line offsets remain correct.
    updated = "".join(lines)
    tree = ast.parse(updated, filename=str(path))
    insertions = _documentation_insertions(updated, tree)
    if insertions:
        updated_lines = updated.splitlines(keepends=True)
        for line_index, text in sorted(insertions, reverse=True):
            updated_lines.insert(line_index, text)
        updated = "".join(updated_lines)
        changed = True

    if changed:
        path.write_text(updated, encoding="utf-8")
    return changed


def main() -> None:
    """Document all repository Python files and report the migration count."""
    changed = sum(document_file(path) for path in _python_files())
    print(f"Documented {changed} Python files.")


if __name__ == "__main__":
    main()
