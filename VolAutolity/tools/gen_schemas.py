"""Generate volautolity/schemas.json: the ADX table schema of every catalog plugin.

Columns and types come from the plugin's own TreeGrid declaration in the installed Volatility
source, so tables can be created up front with stable, declared types instead of guessing them
per image. Run after bumping Volatility in requirements.txt:

    python tools/gen_schemas.py            # rewrite volautolity/schemas.json
    python tools/gen_schemas.py --check    # exit 1 if it is out of date (used by the tests)
"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from volautolity.catalog import PluginCatalog  # noqa: E402
from volautolity.csvnorm import ROW_COLUMN  # noqa: E402
from volautolity.models import OsFamily  # noqa: E402
from volautolity.naming import Identifiers  # noqa: E402

OUTPUT = ROOT / "volautolity" / "schemas.json"

# Column names Volatility builds at runtime; values are what the default options render.
DYNAMIC_NAMES = {
    "f'Offset{offsettype}'": "Offset(V)",
    "offset_str": "Offset(Virtual)",
}

TYPES = {
    "int": "long",
    "str": "string",
    "bool": "bool",
    "float": "real",
    "datetime.datetime": "datetime",
    "datetime": "datetime",
}

# Tables written by VolAutolity itself.
COMMON = {
    "volautolity_runs": [("Plugin", "string"), ("Table", "string"), ("Status", "string"), ("ExitCode", "long"),
                         ("Rows", "long"), ("StartedUtc", "datetime"), ("FinishedUtc", "datetime"),
                         ("DurationSeconds", "real"), ("Error", "string"), ("IngestError", "string")],
    "volautolity_image": [("ImageName", "string"), ("SizeBytes", "long"), ("Sha256", "string"), ("OsFamily", "string"),
                          ("Database", "string"), ("StartedUtc", "datetime"), ("FinishedUtc", "datetime"),
                          ("Tasks", "long"), ("FailedTasks", "long"), ("VolAutolityVersion", "string")],
}
WINDOWS_EXTRA = {
    "clamscan": [("File", "string"), ("DumpedFile", "string"), ("Result", "string"), ("Signature", "string")],
}


def load_plugins() -> dict:
    import volatility3.plugins
    from volatility3 import framework

    framework.require_interface_version(2, 0, 0)
    framework.import_files(volatility3.plugins, True)
    return framework.list_plugins()


def declared_columns(plugin_class) -> list[tuple[str, str]]:
    """Columns from the TreeGrid built in run(), following inheritance to the class that defines run()."""
    owner = next(k for k in plugin_class.__mro__ if "run" in k.__dict__)
    tree = ast.parse(Path(inspect.getsourcefile(owner)).read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == owner.__name__)
    run = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    assignments = {t.targets[0].id: t.value for t in ast.walk(run)
                   if isinstance(t, ast.Assign) and len(t.targets) == 1 and isinstance(t.targets[0], ast.Name)}
    namespace = vars(sys.modules[owner.__module__])
    for call in ast.walk(run):
        if isinstance(call, ast.Call) and ast.unparse(call.func).endswith("TreeGrid"):
            node = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "columns"), None)
            columns = _columns(node, assignments, namespace)
            if columns:
                return columns
    raise LookupError(f"no TreeGrid columns found for {plugin_class.__name__} in {owner.__module__}")


def _attribute_value(node, namespace):
    """Resolve a pure `module.Class.attribute` chain (no calls) against an imported module."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    value = namespace[node.id]
    for part in reversed(parts):
        value = getattr(value, part)
    return value


def _runtime_type(value) -> str:
    import datetime

    return {int: "long", str: "string", bool: "bool", float: "real", datetime.datetime: "datetime"}.get(value, "string")


def _columns(node, assignments, namespace=None) -> list[tuple[str, str]] | None:
    if isinstance(node, ast.Attribute) and namespace is not None:
        value = _attribute_value(node, namespace)
        if isinstance(value, (list, tuple)) and all(isinstance(c, tuple) and len(c) == 2 for c in value):
            return [(name, _runtime_type(kind)) for name, kind in value]
        return None
    if isinstance(node, ast.Name) and node.id in assignments:
        node = assignments[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _columns(node.left, assignments), _columns(node.right, assignments)
        return left + right if left is not None and right is not None else None
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    columns = []
    for element in node.elts:
        if isinstance(element, ast.Starred):
            inner = _columns(element.value, assignments)
            if inner is None:
                return None
            columns += inner
            continue
        if not (isinstance(element, ast.Tuple) and len(element.elts) == 2):
            return None
        name_node, type_node = element.elts
        if isinstance(name_node, ast.Constant):
            name = name_node.value
        elif ast.unparse(name_node) in DYNAMIC_NAMES:
            name = DYNAMIC_NAMES[ast.unparse(name_node)]
        else:
            raise LookupError(f"dynamic column name {ast.unparse(name_node)!r}: add it to DYNAMIC_NAMES")
        columns.append((name, TYPES.get(ast.unparse(type_node), "string")))
    return columns


def build() -> dict:
    plugins = load_plugins()
    catalog = PluginCatalog()
    result: dict[str, dict[str, str]] = {"common": {t: _render(c) for t, c in COMMON.items()}}
    for os_family in OsFamily:
        specs = [catalog.bootstrap(os_family), *catalog.plugins(os_family)]
        tables = {}
        for spec in specs:
            tables[spec.table] = _render(_with_tree_depth(declared_columns(plugins[spec.name])))
        if os_family is OsFamily.WINDOWS:
            tables["printkey_*"] = _render(_with_tree_depth(declared_columns(plugins["windows.registry.printkey.PrintKey"])))
            tables.update({t: _render(c) for t, c in WINDOWS_EXTRA.items()})
        tables[catalog.diagnostics().table] = _render(_with_tree_depth(declared_columns(plugins[catalog.diagnostics().name])))
        result[os_family.value] = dict(sorted(tables.items()))
    return result


def _with_tree_depth(columns):
    return [("TreeDepth", "long"), *columns]


def _render(columns) -> str:
    names = Identifiers.columns([name for name, _ in columns])  # same cleaning as the ingested CSV headers
    rendered = [f"{n}:{t}" for n, (_, t) in zip(names, columns)]
    return ",".join([*rendered, f"{ROW_COLUMN}:long"])  # added to every row by the normaliser


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1) + "\n"
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is out of date: run python tools/gen_schemas.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
