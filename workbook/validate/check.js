// Semantic check of every workbook query with Microsoft's KQL analyzer (Kusto.Language), against the
// table schemas the worker creates (VolAutolity/volautolity/schemas.json). Catches unknown tables or
// columns, type errors and unknown functions before anything is deployed.
//
//   python workbook/build.py --export-queries queries.json
//   node workbook/validate/check.js queries.json VolAutolity/volautolity/schemas.json
"use strict";
const fs = require("fs");
require("@kusto/language-service-next/bridge.min");
require("@kusto/language-service-next/Kusto.Language.Bridge.min");

const [queriesFile, schemaFile] = process.argv.slice(2);
const queries = JSON.parse(fs.readFileSync(queriesFile, "utf8"));
const schemas = JSON.parse(fs.readFileSync(schemaFile, "utf8"));
const S = Kusto.Language.Symbols;

// Windows tables + VolAutolity's own tables. printkey_* is a pattern: create the usual hive tables.
const tables = Object.assign({}, schemas.common, schemas.windows);
const hives = ["SOFTWARE", "SYSTEM", "SAM", "SECURITY", "DEFAULT", "ntuser", "ntuser2", "UsrClass", "UsrClass2", "BCD", "UnnamedKey"];
for (const hive of hives) tables[`printkey_${hive}`] = tables["printkey_*"];
delete tables["printkey_*"];

const symbols = Object.entries(tables).map(([name, spec]) => {
  const schema = "(" + spec.split(",").map(c => { const [n, t] = c.split(":"); return `['${n}']:${t}`; }).join(", ") + ")";
  return new S.TableSymbol.$ctor7(name, schema, "");
});
const database = new S.DatabaseSymbol.$ctor1("image", symbols);
const globals = Kusto.Language.GlobalState.Default.WithDatabase(database);

let failures = 0;
for (const { name, query } of queries) {
  const code = Kusto.Language.KustoCode.ParseAndAnalyze(query, globals);
  const diagnostics = code.GetDiagnostics();
  const problems = [];
  for (let i = 0; i < diagnostics.Count; i++) {
    const d = diagnostics.getItem(i);
    if (String(d.Severity) !== "Error") continue;
    const before = query.slice(0, d.Start);
    const line = before.split("\n").length;
    const lineText = query.split("\n")[line - 1];
    problems.push(`  line ${line}: ${d.Message}\n      ${lineText.trim()}`);
  }
  if (problems.length) {
    failures++;
    console.log(`FAIL ${name}\n${problems.join("\n")}`);
  }
}
console.log(`${queries.length - failures}/${queries.length} queries OK`);
process.exit(failures ? 1 : 0);
