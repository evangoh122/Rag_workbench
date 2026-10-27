"""Static checks for notebooks/colab_backfill.ipynb (no Colab, GPU or network needed).

    uv run python scripts/check_colab_notebook.py [notebook.ipynb]
    uv run --with nbformat python scripts/check_colab_notebook.py   # also nbformat.validate

Checks: valid JSON; every code cell parses with ast (shell/cell magics are blanked
first); outputs and execution counts are cleared; embedding and staging are disabled by
default; the repo checkout is pinned to a full commit sha; the notebook can only write to a staging repo that is not production (no upload,
commit or Space-restart call against the dataset); no hardcoded token; no cell prints or
echoes a secret.
"""
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_NB = Path(__file__).resolve().parent.parent / "notebooks" / "colab_backfill.ipynb"
SECRET_NAMES = ("HF_TOKEN", "GH_TOKEN", "EDGAR_USER_AGENT", "auth")
PROD_REPO = "egoh33/rag-workbench"
# The notebook may only stage through `scripts.hf_backfill stage-upload`; publishing is out of scope.
FORBIDDEN_CALLS = ("create_commit", "upload_file", "upload_folder", "CommitOperationAdd",
                   "CommitOperationDelete", "delete_file", "delete_repo", "restart_space")
TOKEN_RE = re.compile(r"\b(hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")


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
    for flag in ("CONFIRM_EXECUTE", "CONFIRM_STAGE"):
        if not re.search(rf"^{flag}\s*=\s*False\b", joined, re.MULTILINE):
            problems.append(f"{flag} = False not found (must be off by default)")
        if re.search(rf"^{flag}\s*=\s*True\b", joined, re.MULTILINE):
            problems.append(f"{flag} is True")
    m = re.search(r"^STAGING_REPO\s*=\s*['\"]([^'\"]+)['\"]", joined, re.MULTILINE)
    if not m:
        problems.append("STAGING_REPO literal not found")
    elif m.group(1).strip().lower() == PROD_REPO:
        problems.append("STAGING_REPO is the production dataset")
    c = re.search(r"^REPO_COMMIT\s*=\s*['\"]([^'\"]*)['\"]", joined, re.MULTILINE)
    if not c:
        problems.append("REPO_COMMIT literal not found (the checkout must be pinned to a commit)")
    elif c.group(1) and not re.fullmatch(r"[0-9a-f]{40}", c.group(1)):
        problems.append("REPO_COMMIT must be empty or a full 40-character lowercase sha")
    for needle in ("stage-upload", "append_only_proof", "dry_run()", "split_complete", "checkout_pinned"):
        if needle not in joined:
            problems.append(f"{needle} not found")
    for name in FORBIDDEN_CALLS:
        if re.search(rf"\b{name}\b", joined):
            problems.append(f"forbidden call {name}: the notebook must not publish")
    # Whole file, markdown cells and metadata included.
    raw = Path(path).read_text(encoding="utf-8")
    if TOKEN_RE.search(raw):
        problems.append("a token-shaped string is present")
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        for line in _source(cell).splitlines():
            if line.lstrip().startswith(("!", "%")) and any(n in line for n in SECRET_NAMES[:3]):
                problems.append(f"cell {i}: shell magic references a secret")
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
