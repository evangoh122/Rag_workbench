"""Static checks for notebooks/colab_backfill.ipynb (no Colab, GPU or network needed).

    uv run python scripts/check_colab_notebook.py [notebook.ipynb]
    uv run --with nbformat python scripts/check_colab_notebook.py   # also nbformat.validate

Checks: valid JSON; every code cell parses with ast (shell/cell magics are blanked
first); outputs and execution counts are cleared; embedding and staging are disabled by
default (the LAST assignment of each flag, in cell order, must be a literal False); the repo
checkout is pinned to a full commit sha; the notebook can only write to a staging repo that is not
production (no upload, commit or Space-restart call against the dataset, and no executable
`scripts.hf_backfill publish` command); the required steps are real calls, in order (the append-only
proof before stage-upload), not marker text; no hardcoded token; no cell prints or echoes a secret
(including `os.environ["HF_TOKEN"]` / `userdata.get("HF_TOKEN")` read by key).
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
# A name containing a space is a shell command, matched only in executable code (a print() that
# tells the user how to publish from a checkout is allowed).
FORBIDDEN_CALLS = ("create_commit", "upload_file", "upload_folder", "CommitOperationAdd",
                   "CommitOperationDelete", "delete_file", "delete_repo", "restart_space",
                   "scripts.hf_backfill publish")
PUBLISH_CMD_RE = re.compile(r"hf_backfill(?:\.py)?\s+publish\b")
FLAGS = ("CONFIRM_EXECUTE", "CONFIRM_STAGE")
# Steps that must be real calls: (call name, label). stage-upload is matched as a command argument.
REQUIRED_CALLS = ("checkout_pinned", "dry_run", "split_complete", "append_only_proof")
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


def _reads_secret(node: ast.AST) -> bool:
    """True when a node names a secret directly or reads one by a constant key."""
    if isinstance(node, ast.Name):
        return node.id in SECRET_NAMES
    key = None
    if isinstance(node, ast.Subscript):  # os.environ["HF_TOKEN"]
        key = node.slice
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
          and node.func.attr in ("get", "getenv") and node.args):  # userdata.get("HF_TOKEN")
        key = node.args[0]
    elif (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getenv" and node.args):
        key = node.args[0]
    return isinstance(key, ast.Constant) and key.value in SECRET_NAMES


def _callee(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _flag_assignments(tree: ast.AST, flag: str):
    """(lineno, col, value) for every assignment to `flag`; value is the Constant's value, or
    `_NOT_LITERAL` when it is anything else (bool(1), a tuple unpack, +=, ...)."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == flag:
                    out.append((n.lineno, n.col_offset,
                                n.value.value if isinstance(n.value, ast.Constant) else _NOT_LITERAL))
                elif any(isinstance(x, ast.Name) and x.id == flag and isinstance(x.ctx, ast.Store)
                         for x in ast.walk(t)):
                    out.append((n.lineno, n.col_offset, _NOT_LITERAL))
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == flag and n.value:
            out.append((n.lineno, n.col_offset,
                        n.value.value if isinstance(n.value, ast.Constant) else _NOT_LITERAL))
        elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == flag:
            out.append((n.lineno, n.col_offset, _NOT_LITERAL))
    return out


_NOT_LITERAL = object()


def _publishes(tree: ast.AST) -> bool:
    """True when executable code (anything outside a print() call) holds a `hf_backfill publish` command."""
    skip: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and _callee(n) == "print":
            skip.update(id(x) for x in ast.walk(n))
    for n in ast.walk(tree):
        if id(n) in skip:
            continue
        if isinstance(n, (ast.List, ast.Tuple)):
            text = " ".join(e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            text = n.value
        else:
            continue
        if PUBLISH_CMD_RE.search(text):
            return True
    return False


def check_notebook(path: Path) -> list[str]:
    """Return a list of problems (empty means the notebook is clean)."""
    problems: list[str] = []
    nb = json.loads(Path(path).read_text(encoding="utf-8"))
    if nb.get("nbformat") != 4:
        problems.append(f"nbformat is {nb.get('nbformat')!r}, expected 4")

    code_cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
    if not code_cells:
        problems.append("no code cells")
    trees: list[tuple[int, ast.AST]] = []  # (cell index, parsed tree) in cell order
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
        trees.append((i, tree))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"
                    and any(_reads_secret(n) for a in node.args for n in ast.walk(a))):
                problems.append(f"cell {i}: print() references a secret variable")

    joined = "\n".join(_source(c) for c in code_cells)
    for flag in FLAGS:
        # Cell order, then position in the cell: the LAST assignment is the value later cells see.
        assigns = [(i, ln, col, v) for i, tree in trees for ln, col, v in _flag_assignments(tree, flag)]
        assigns.sort(key=lambda a: a[:3])
        if not assigns:
            problems.append(f"{flag} = False not found (must be off by default)")
        elif assigns[-1][3] is not False:
            final = assigns[-1][3]
            problems.append(f"{flag} is True" if final is True
                            else f"{flag} final assignment is not a literal False")
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
    # The required steps must be executable calls, not marker text, and the proof must come first.
    first_call: dict[str, tuple[int, int, int]] = {}
    for i, tree in trees:
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            pos = (i, n.lineno, n.col_offset)
            names = [_callee(n)]
            if any(isinstance(x, ast.Constant) and x.value == "stage-upload" for x in ast.walk(n)):
                names.append("stage-upload")
            for name in names:
                if name in REQUIRED_CALLS + ("stage-upload",) and (name not in first_call or pos < first_call[name]):
                    first_call[name] = pos
    for name in REQUIRED_CALLS + ("stage-upload",):
        if name not in first_call:
            problems.append(f"call to {name} not found (a marker string does not count)")
    if "stage-upload" in first_call and "append_only_proof" in first_call \
            and first_call["append_only_proof"] >= first_call["stage-upload"]:
        problems.append("append_only_proof must run before stage-upload")
    publishes = any(_publishes(tree) for _, tree in trees) or any(
        PUBLISH_CMD_RE.search(line) for c in code_cells for line in _source(c).splitlines()
        if line.lstrip().startswith(("!", "%")))
    for name in FORBIDDEN_CALLS:
        hit = publishes if " " in name else re.search(rf"\b{re.escape(name)}\b", joined)
        if hit:
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
