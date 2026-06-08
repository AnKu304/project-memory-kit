from __future__ import annotations

import json
from typing import Any


def _safe_json_script(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def render_human_graph_html(data: dict[str, Any]) -> str:
    payload = _safe_json_script(data)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Human Memory Graph</title>
<style>
body {{ margin: 0; font: 14px system-ui, sans-serif; color: #1f2937; background: #f8fafc; }}
header {{ padding: 16px 20px; background: #111827; color: white; }}
main {{ display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 64px); }}
aside {{ padding: 16px; border-right: 1px solid #d1d5db; background: white; }}
label {{ display: block; margin: 0 0 12px; font-weight: 600; }}
select, input {{ width: 100%; box-sizing: border-box; margin-top: 6px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 6px; }}
svg {{ width: 100%; height: calc(100vh - 64px); background: #f8fafc; }}
.node circle {{ stroke: #111827; stroke-width: 1.2; }}
.node text {{ font-size: 12px; paint-order: stroke; stroke: #f8fafc; stroke-width: 4px; }}
.edge {{ stroke: #94a3b8; stroke-width: 1.4; marker-end: url(#arrow); }}
</style>
</head>
<body>
<header><h1>Human Memory Graph</h1></header>
<main>
<aside>
<label>Layer<select id="layerFilter"><option value="">All</option></select></label>
<label>Type<select id="typeFilter"><option value="">All</option></select></label>
<label>Status<select id="statusFilter"><option value="">All</option></select></label>
<label>Search<input id="searchFilter" placeholder="Title or id"></label>
<p id="summary"></p>
</aside>
<svg id="graph" role="img" aria-label="Human memory graph"></svg>
</main>
<script>
const data = {payload};
const svg = document.getElementById("graph");
const filters = ["layer", "type", "status"];
for (const name of filters) {{
  const select = document.getElementById(name + "Filter");
  [...new Set(data.nodes.map((node) => node[name]).filter(Boolean))].sort()
    .forEach((value) => select.insertAdjacentHTML("beforeend", `<option>${{value}}</option>`));
  select.addEventListener("change", render);
}}
document.getElementById("searchFilter").addEventListener("input", render);
function visibleNodes() {{
  const search = document.getElementById("searchFilter").value.toLowerCase();
  return data.nodes.filter((node) =>
    filters.every((name) => !document.getElementById(name + "Filter").value ||
      node[name] === document.getElementById(name + "Filter").value) &&
    (!search || node.title.toLowerCase().includes(search) || node.id.toLowerCase().includes(search))
  );
}}
function color(layer) {{ return {{knowledge:"#2563eb", rationale:"#7c3aed", external:"#64748b"}}[layer] || "#0f766e"; }}
function render() {{
  const nodes = visibleNodes();
  const visible = new Set(nodes.map((node) => node.id));
  const edges = data.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target));
  const width = svg.clientWidth || 900, height = svg.clientHeight || 600;
  const cx = width / 2, cy = height / 2, r = Math.max(120, Math.min(width, height) / 2 - 80);
  const pos = new Map(nodes.map((node, i) => [node.id, {{
    x: cx + r * Math.cos((2 * Math.PI * i) / Math.max(nodes.length, 1)),
    y: cy + r * Math.sin((2 * Math.PI * i) / Math.max(nodes.length, 1))
  }}]));
  svg.innerHTML = '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#94a3b8"/></marker></defs>';
  for (const edge of edges) {{
    const a = pos.get(edge.source), b = pos.get(edge.target);
    svg.insertAdjacentHTML("beforeend", `<line class="edge" x1="${{a.x}}" y1="${{a.y}}" x2="${{b.x}}" y2="${{b.y}}"><title>${{edge.relation}}</title></line>`);
  }}
  for (const node of nodes) {{
    const p = pos.get(node.id);
    svg.insertAdjacentHTML("beforeend", `<g class="node"><circle cx="${{p.x}}" cy="${{p.y}}" r="8" fill="${{color(node.layer)}}"></circle><text x="${{p.x + 12}}" y="${{p.y + 4}}">${{node.title}}</text><title>${{node.id}}\\n${{node.path || ""}}</title></g>`);
  }}
  document.getElementById("summary").textContent = `${{nodes.length}} nodes, ${{edges.length}} edges`;
}}
render();
</script>
</body>
</html>
"""
