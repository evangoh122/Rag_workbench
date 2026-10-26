"""Static checks for notebooks/colab_backfill.ipynb (no Colab, GPU or network needed).

    uv run python scripts/check_colab_notebook.py [notebook.ipynb]
    uv run --with nbformat python scripts/check_colab_notebook.py   # also nbformat.validate

Checks: valid JSON; every code cell parses with ast (shell/cell magics are blanked
first); outputs and execution counts are cleared; publish is disabled by default;
no cell prints a secret variable.
"""
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_NB = Path(__file__).resolve().parent.parent / "notebooks" / "colab_backfill.ipynb"
SECRET_NAMES = ("HF_TOKEN", "GH_TOKEN", "auth")


def _source(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def _blank_magics(code: str) -> str:
    """Replace IPython `!cmd` / `%magic` lines with `pass` so ast can parse the rest."""
    lines = []
    for line in code.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("!", "%")):
            line = line[: len(line) - len(stripped)] + "pass"
        lines.append(line)
    return "\n".join(lines)


def check_notebook(path: Path) -> list[str]:
    """Return a list of problems (empty means the notebook is clean)."""
    problems: list[str] = []
    nb = json.loads(Path(path).read_text(encoding="utf-8"))
    if nb.get("nbformat") != 4:
        problems.append(f"nbformat is {nb.get('nbformat')!r}, expected 4")

    code_cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
    if not code_cells:
        problems.append("no code cells")
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        code = _source(cell)
        if cell.get("outputs"):
            problems.append(f"cell {i}: outputs not cleared")
        if cell.get("execution_count") is not None:
            problems.append(f"cell {i}: execution_count not cleared")
        try:
            tree = ast.parse(_blank_magics(code))
        except SyntaxError as exc:
            problems.append(f"cell {i}: SyntaxError line {exc.lineno}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"
                    and any(isinstance(n, ast.Name) and n.id in SECRET_NAMES
                            for a in node.args for n in ast.walk(a))):
                problems.append(f"cell {i}: print() references a secret variable")

    joined = "\n".join(_source(c) for c in code_cells)
    if not re.search(r"^CONFIRM_PUBLISH\s*=\s*False\b", joined, re.MULTILINE):
        problems.append("CONFIRM_PUBLISH = False not found (publish must be off by default)")
    if re.search(r"^CONFIRM_PUBLISH\s*=\s*True\b", joined, re.MULTILINE):
        problems.append("CONFIRM_PUBLISH is True")
    if "parent_commit" not in joined:
        problems.append("publish must use create_commit with parent_commit")
    return problems


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_NB
    problems = check_notebook(path)
    try:
        import nbformat
        nbformat.validate(nbformat.read(str(path), as_version=4))
        print("nbformat.validate: OK")
    except ImportError:
        print("nbformat not installed; skipped nbformat.validate")
    except Exception as exc:  # nbformat.ValidationError
        problems.append(f"nbformat.validate: {exc}")
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print(f"{path.name}: OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
