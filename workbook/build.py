"""Build the Azure Workbook (cfg/windows_triage.json) from the KQL sources in this directory.

    workbook/lib/<Name>.kql        shared `let Name = ...;` definitions, prepended automatically to every
                                   query that references Name (transitively), so each workbook query is
                                   self-contained and can be pasted into ADX as-is
    workbook/tabs/<NN-key>/tab.md  tab title (first line, "# Title") and intro text
    workbook/tabs/<NN-key>/params.json   optional workbook parameters shown at the top of the tab
    workbook/tabs/<NN-key>/<NNN-slug>.kql   one workbook query each, with a metadata header:

        // Title: Processes running from staging directories
        // Severity: High                          (shown as a badge; optional)
        // Visualization: table | tiles | barchart | piechart | timechart | map | tree
        // Size: small | medium | large | full    (optional, default medium)
        // Why: one paragraph of analyst guidance
        // FalsePositives: known benign causes     (optional)
        // MITRE: T1036.005, T1055                 (optional)
        // Refs: https://... ; https://...         (optional)
        // Tiles: number | text                   (tiles only; default text)
        // NoData: message shown when the query returns nothing (optional)
        // Tree: id=PID parent=PPID label=Process  (only for Visualization: tree)
        // Map: lat=Latitude lon=Longitude label=ForeignAddr size=Connections  (only for map)
        <KQL>

    python workbook/build.py                       write cfg/windows_triage.json
    python workbook/build.py --check               fail if the committed JSON is stale
    python workbook/build.py --export-queries F    write expanded queries (parameters substituted) for
                                                   workbook/validate/check.js
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "cfg" / "windows_triage.json"
NAMESPACE = uuid.UUID("2f6c3c49-3f39-4a8e-9b8a-7a7e3c0f6d11")  # stable ids => stable diffs

# Values the OpenTofu templatefile() call fills in (cfg/workbook.tf). Everything else that looks like
# a template sequence is escaped so templatefile() leaves it alone.
TEMPLATE_VARS = {"__CLUSTER_URL__": "${cluster_url}", "__RESOURCE_GROUP_ID__": "${resource_group_id}",
                 "__FALLBACK_RESOURCE_ID__": "${fallback_resource_id}"}

SIZES = {"medium": 0, "small": 1, "large": 2, "full": 3, "tiny": 4}
SEVERITY_BADGE = {"critical": "🟥 Critical", "high": "🟧 High", "medium": "🟨 Medium", "low": "🟦 Low", "info": "⬜ Info"}
VISUALIZATIONS = {"table", "tiles", "barchart", "piechart", "timechart", "map", "tree"}


@dataclass
class Query:
    path: Path
    title: str
    body: str
    meta: dict[str, str]

    @property
    def key(self) -> str:
        return f"{self.path.parent.name}/{self.path.stem}"


@dataclass
class Tab:
    key: str
    title: str
    intro: str
    queries: list[Query] = field(default_factory=list)
    params: list[dict] = field(default_factory=list)


class Library:
    """Shared `let` definitions, resolved by name and included in dependency order."""

    def __init__(self, directory: Path):
        self.definitions = {p.stem: p.read_text(encoding="utf-8").strip() for p in sorted(directory.glob("*.kql"))}
        for name, text in self.definitions.items():
            if not re.match(rf"^(//.*\n)*let\s+{re.escape(name)}\s*=", text):
                raise ValueError(f"lib/{name}.kql must define `let {name} = ...`")

    def _uses(self, text: str) -> list[str]:
        code = "\n".join(line.split("//", 1)[0] for line in text.splitlines())  # ignore comments
        return [name for name in self.definitions if re.search(rf"(?<![\w.]){re.escape(name)}(?!\w)", code)]

    def expand(self, body: str) -> str:
        ordered: list[str] = []

        def visit(name: str, stack: tuple[str, ...]) -> None:
            if name in ordered:
                return
            if name in stack:
                raise ValueError(f"circular lib dependency: {' -> '.join(stack + (name,))}")
            for dep in self._uses(self.definitions[name].split("=", 1)[1]):
                if dep != name:
                    visit(dep, stack + (name,))
            ordered.append(name)

        for name in self._uses(body):
            visit(name, ())
        # The readable source lives in lib/; what ships in the workbook drops full-line comments and
        # indentation to keep the workbook small (every query carries its own copy of the definitions).
        preamble = "\n".join(_compact(self.definitions[name]) for name in ordered)
        return f"{preamble}\n{body}" if preamble else body


def _compact(kql: str) -> str:
    lines = (line.strip() for line in kql.splitlines())
    return "\n".join(line for line in lines if line and not line.startswith("//"))


def parse_query(path: Path) -> Query:
    meta: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines) and lines[index].startswith("//"):
        match = re.match(r"^//\s*([A-Za-z]+):\s*(.*)$", lines[index])
        if match:
            meta[match.group(1).lower()] = match.group(2).strip()
        elif meta:  # continuation line of the previous key
            last = next(reversed(meta))
            meta[last] += " " + lines[index].lstrip("/ ").strip()
        index += 1
    body = "\n".join(lines[index:]).strip()
    if "title" not in meta or not body:
        raise ValueError(f"{path}: needs a '// Title:' header and a query body")
    viz = meta.get("visualization", "table")
    if viz not in VISUALIZATIONS:
        raise ValueError(f"{path}: unknown visualization {viz!r}")
    return Query(path, meta["title"], body, meta)


def load_tabs() -> list[Tab]:
    tabs = []
    for directory in sorted(p for p in (ROOT / "tabs").iterdir() if p.is_dir()):
        intro = (directory / "tab.md").read_text(encoding="utf-8").strip()
        title, _, rest = intro.partition("\n")
        tab = Tab(key=directory.name.split("-", 1)[1], title=title.lstrip("# ").strip(), intro=rest.strip())
        tab.queries = [parse_query(p) for p in sorted(directory.glob("*.kql"))]
        params = directory / "params.json"
        if params.exists():
            tab.params = json.loads(params.read_text(encoding="utf-8"))
        tabs.append(tab)
    return tabs


class WorkbookBuilder:
    def __init__(self, tabs: list[Tab], library: Library):
        self.tabs = tabs
        self.library = library

    def build(self) -> dict:
        items = [
            self._cluster_parameter(),
            self._text("header", "# Memory forensics triage\nPick an image (one database per image). "
                       "Start with **Overview**: what ran, what failed, and the highest-scoring findings. "
                       "Every finding explains why it matters and what commonly causes false positives."),
            self._database_parameter(),
            self._tab_links(),
        ]
        items += [self._tab_group(tab) for tab in self.tabs]
        return {
            "version": "Notebook/1.0",
            "items": items,
            "fallbackResourceIds": ["__FALLBACK_RESOURCE_ID__"],
            "$schema": "https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json",
        }

    # -- items -------------------------------------------------------------------------------------

    def _id(self, *parts: str) -> str:
        return str(uuid.uuid5(NAMESPACE, "/".join(parts)))

    def _cluster_parameter(self) -> dict:
        return {"type": 9, "name": "parameters - cluster", "content": {
            "version": "KqlParameterItem/1.0", "crossComponentResources": ["__RESOURCE_GROUP_ID__"],
            "parameters": [{"id": self._id("param", "Clustername"), "version": "KqlParameterItem/1.0",
                            "name": "Clustername", "type": 1, "description": "ADX cluster URI",
                            "isRequired": True, "isHiddenWhenLocked": True, "value": "__CLUSTER_URL__"}],
            "style": "formVertical", "queryType": 0, "resourceType": "microsoft.operationalinsights/workspaces"}}

    def _database_parameter(self) -> dict:
        query = (".show databases\n| where DatabaseName !in ('$systemdb')\n"
                 "| project DatabaseName\n| order by DatabaseName desc")
        return {"type": 9, "name": "parameters - database", "content": {
            "version": "KqlParameterItem/1.0",
            "parameters": [{"id": self._id("param", "Databases"), "version": "KqlParameterItem/1.0",
                            "name": "Databases", "label": "Memory image (database)", "type": 2,
                            "description": "One database per analysed memory image", "isRequired": True,
                            "query": self._adx_query(query, database=False),
                            "typeSettings": {"additionalResourceOptions": [], "showDefault": False},
                            "queryType": 9, "value": None}],
            "style": "above", "queryType": 9}}

    def _tab_links(self) -> dict:
        links = [{"id": self._id("tab", tab.key), "cellValue": "setTab", "linkTarget": "parameter",
                  "linkLabel": tab.title, "subTarget": tab.key, "style": "link"} for tab in self.tabs]
        return {"type": 11, "name": "tabs", "content": {"version": "LinkItem/1.0", "style": "tabs", "links": links}}

    def _tab_group(self, tab: Tab) -> dict:
        items = [self._text(f"{tab.key}-intro", f"## {tab.title}\n{tab.intro}")]
        if tab.params:
            items.append(self._tab_parameters(tab))
        for query in tab.queries:
            items.append(self._text(f"{query.key}-help", self._help(query)))
            items.append(self._query_item(query))
        return {"type": 12, "name": tab.key,
                "content": {"version": "NotebookGroup/1.0", "groupType": "editable", "items": items},
                "conditionalVisibility": {"parameterName": "setTab", "comparison": "isEqualTo", "value": tab.key}}

    def _tab_parameters(self, tab: Tab) -> dict:
        parameters = []
        for param in tab.params:
            spec = {k: v for k, v in param.items() if k not in ("testValue", "kql")}
            spec.setdefault("version", "KqlParameterItem/1.0")
            spec["id"] = self._id("param", tab.key, param["name"])
            if "kql" in param:
                spec["query"] = self._adx_query(self.library.expand(param["kql"]))
                spec["queryType"] = 9
                spec.setdefault("typeSettings", {"additionalResourceOptions": [], "showDefault": False})
            parameters.append(spec)
        return {"type": 9, "name": f"{tab.key}-parameters",
                "content": {"version": "KqlParameterItem/1.0", "parameters": parameters, "style": "pills", "queryType": 9}}

    def _help(self, query: Query) -> str:
        meta = query.meta
        heading = f"### {query.title}"
        if meta.get("severity"):
            heading += f" &nbsp; `{SEVERITY_BADGE.get(meta['severity'].lower(), meta['severity'])}`"
        lines = [heading]
        if meta.get("why"):
            lines.append(meta["why"])
        if meta.get("falsepositives"):
            lines.append(f"**False positives / edge cases:** {meta['falsepositives']}")
        tail = []
        if meta.get("mitre"):
            tail.append("ATT&CK: " + ", ".join(
                f"[{t}](https://attack.mitre.org/techniques/{t.replace('.', '/')}/)" for t in re.split(r"[,\s]+", meta["mitre"]) if t))
        if meta.get("refs"):
            tail.append("Refs: " + " · ".join(f"[{i + 1}]({u.strip()})" for i, u in enumerate(meta["refs"].split(";")) if u.strip()))
        if tail:
            lines.append("<sub>" + " &nbsp;|&nbsp; ".join(tail) + "</sub>")
        return "\n\n".join(lines)

    def _query_item(self, query: Query) -> dict:
        viz = query.meta.get("visualization", "table")
        content: dict = {
            "version": "KqlItem/1.0",
            "query": self._adx_query(self.library.expand(query.body)),
            "size": SIZES[query.meta.get("size", "medium").lower()],
            "queryType": 9,
            "noDataMessage": query.meta.get("nodata", "Nothing found (or the plugin produced no data for this image)."),
            "showExportToExcel": True,
        }
        if viz == "tree":
            settings = dict(item.split("=", 1) for item in query.meta["tree"].split())
            content["visualization"] = "table"
            content["gridSettings"] = {**self._grid_settings(),
                                       "hierarchySettings": {"idColumn": settings["id"], "parentColumn": settings["parent"],
                                                             "treeType": 0, "expanderColumn": settings["label"],
                                                             "expandTopLevel": True}}
        elif viz == "map":
            settings = dict(item.split("=", 1) for item in query.meta["map"].split())
            content["visualization"] = "map"
            content["mapSettings"] = {"locInfo": "LatLong", "latitude": settings["lat"], "longitude": settings["lon"],
                                      "sizeSettings": settings["size"], "sizeAggregation": "Sum",
                                      "labelSettings": settings["label"], "legendMetric": settings["size"],
                                      "legendAggregation": "Sum", "itemColorSettings": {"type": "heatmap",
                                      "colorAggregation": "Sum", "nodeColorField": settings["size"], "heatmapPalette": "greenRed"}}
        elif viz == "tiles":
            numeric = query.meta.get("tiles", "text").lower() == "number"
            content["visualization"] = "tiles"
            content["tileSettings"] = {"titleContent": {"columnMatch": "Title", "formatter": 1},
                                       "leftContent": {"columnMatch": "Value", "formatter": 12 if numeric else 1,
                                                       "formatOptions": {"palette": "redBright" if numeric else "none"}},
                                       "secondaryContent": {"columnMatch": "Subtitle", "formatter": 1},
                                       "showBorder": True}
        else:
            content["visualization"] = viz
            if viz == "table":
                content["gridSettings"] = self._grid_settings()
        return {"type": 3, "name": query.key, "content": content}

    @staticmethod
    def _grid_settings() -> dict:
        colours = {"Critical": "redBright", "High": "orange", "Medium": "yellow", "Low": "blue", "Info": "gray"}
        grid = [{"operator": "==", "thresholdValue": sev, "representation": colour, "text": "{0}{1}"}
                for sev, colour in colours.items()]
        grid.append({"operator": "Default", "thresholdValue": None, "representation": None, "text": "{0}{1}"})
        return {"formatters": [{"columnMatch": "Severity", "formatter": 18,
                                "formatOptions": {"thresholdsOptions": "colors", "thresholdsGrid": grid}}],
                "filter": True}

    @staticmethod
    def _adx_query(text: str, database: bool = True) -> str:
        payload = {"version": "AzureDataExplorerQuery/1.0", "queryText": text, "clusterName": "{Clustername}"}
        if database:
            payload["databaseName"] = "{Databases}"
        return json.dumps(payload)

    def _text(self, name: str, markdown: str) -> dict:
        return {"type": 1, "name": f"text - {name}", "content": {"json": markdown}}


def render(workbook: dict) -> str:
    text = json.dumps(workbook, indent=2, ensure_ascii=False) + "\n"
    # Escape OpenTofu template sequences in content, then put the real template variables in.
    text = text.replace("${", "$${").replace("%{", "%%{")
    for placeholder, variable in TEMPLATE_VARS.items():
        text = text.replace(placeholder, variable)
    return text


def export_queries(tabs: list[Tab], library: Library, path: Path) -> None:
    """Fully expanded queries with workbook parameters replaced by test values, for check.js."""
    exported = []
    for tab in tabs:
        test_values = {p["name"]: str(p.get("testValue", "")) for p in tab.params}
        for param in tab.params:
            if "kql" in param:
                exported.append({"name": f"{tab.key}/params.json:{param['name']}", "query": library.expand(param["kql"])})
        for query in tab.queries:
            text = library.expand(query.body)
            for name, value in test_values.items():
                text = text.replace("{" + name + "}", value)
            exported.append({"name": query.key, "query": text})
    path.write_text(json.dumps(exported, indent=1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--export-queries", type=Path)
    args = parser.parse_args()
    tabs, library = load_tabs(), Library(ROOT / "lib")
    if args.export_queries:
        export_queries(tabs, library, args.export_queries)
        print(f"exported queries to {args.export_queries}")
        return 0
    text = render(WorkbookBuilder(tabs, library).build())
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != text:
            print(f"{OUTPUT} is stale: run python workbook/build.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({sum(len(t.queries) for t in tabs)} queries in {len(tabs)} tabs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
