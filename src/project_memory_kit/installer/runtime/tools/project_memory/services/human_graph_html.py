from __future__ import annotations

import json
from typing import Any

from tools.project_memory.services.human_graph_html_script import SCRIPT


def _safe_json_script(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Human Memory Graph</title>
"""


STYLE = """<style>
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #171923;
  --muted: #667085;
  --line: #d9dee7;
  --stage: #10141e;
  --stage-soft: #161b28;
  --knowledge: #2f6fed;
  --rationale: #8a5cf6;
  --external: #f2b84b;
  --human: #18a999;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  overflow: hidden;
  font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--ink);
  background: var(--bg);
}
header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px 0 24px;
  color: #f8fafc;
  background: #111827;
  border-bottom: 1px solid #2b3342;
}
h1 { margin: 0; font-size: 22px; line-height: 1; letter-spacing: 0; }
main {
  display: grid;
  grid-template-columns: minmax(260px, 300px) minmax(0, 1fr);
  min-height: calc(100vh - 64px);
}
aside {
  min-width: 0;
  padding: 16px;
  overflow: auto;
  border-right: 1px solid var(--line);
  background: var(--panel);
}
label {
  display: block;
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 700;
  color: #344054;
}
select,
input {
  width: 100%;
  min-height: 38px;
  margin-top: 6px;
  padding: 8px 10px;
  color: #111827;
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
}
button {
  min-height: 36px;
  padding: 0 12px;
  color: #111827;
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  cursor: pointer;
}
button:hover { border-color: #94a3b8; }
button:disabled { cursor: not-allowed; opacity: 0.58; }
.toggle { display: flex; align-items: center; gap: 8px; margin: 4px 0 16px; color: #344054; }
.toggle input { width: auto; min-height: auto; margin: 0; }
.stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 16px 0;
}
.metric {
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fafc;
}
.metric b { display: block; font-size: 20px; line-height: 1.1; }
.metric span { color: var(--muted); font-size: 12px; }
.legend {
  display: grid;
  gap: 7px;
  margin: 16px 0;
  color: #344054;
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.dot { width: 10px; height: 10px; border-radius: 999px; }
.details {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.details h2 { margin: 0 0 8px; font-size: 15px; }
.details p { margin: 0 0 8px; color: var(--muted); overflow-wrap: anywhere; }
.stage { position: relative; min-width: 0; background: var(--stage); }
.toolbar {
  position: absolute;
  z-index: 2;
  top: 14px;
  right: 14px;
  display: flex;
  gap: 8px;
}
.toolbar button {
  color: #e5e7eb;
  background: rgba(17, 24, 39, 0.82);
  border-color: rgba(148, 163, 184, 0.28);
  backdrop-filter: blur(10px);
}
#graph {
  width: 100%;
  height: calc(100vh - 64px);
  display: block;
  cursor: grab;
  background:
    radial-gradient(circle at 25% 20%, rgba(47, 111, 237, 0.10), transparent 26%),
    radial-gradient(circle at 78% 72%, rgba(242, 184, 75, 0.10), transparent 24%),
    linear-gradient(180deg, var(--stage-soft), var(--stage));
  touch-action: none;
}
#graph:active { cursor: grabbing; }
.edge {
  stroke: #64748b;
  stroke-width: 1.15;
  stroke-opacity: 0.55;
  vector-effect: non-scaling-stroke;
}
.edge.evidence {
  stroke: #f2b84b;
  stroke-dasharray: 5 5;
  animation: dash 18s linear infinite;
}
.edge.active { stroke-opacity: 0.95; stroke-width: 2; }
.node circle {
  stroke: rgba(255,255,255,0.88);
  stroke-width: 1.4;
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.35));
}
.node text {
  font-size: 12px;
  fill: #f8fafc;
  stroke: rgba(16,20,30,0.88);
  stroke-width: 4px;
  paint-order: stroke;
  pointer-events: none;
}
.node.external text { opacity: 0.72; }
.node.dim, .edge.dim { opacity: 0.16; }
.node.active circle { stroke: #ffffff; stroke-width: 2.4; }
.empty {
  fill: #cbd5e1;
  font-size: 16px;
}
@keyframes dash { to { stroke-dashoffset: -120; } }
@media (max-width: 760px) {
  body { overflow: auto; }
  main { grid-template-columns: 1fr; }
  aside { max-height: 44vh; border-right: 0; border-bottom: 1px solid var(--line); }
  #graph { height: 56vh; }
  .toolbar { top: 10px; right: 10px; }
}
</style>
"""


BODY = """</head>
<body>
<header>
  <h1>Human Memory Graph</h1>
  <div id="headerSummary"></div>
</header>
<main>
<aside>
  <label>Layer<select id="layerFilter"><option value="">All</option></select></label>
  <label>Type<select id="typeFilter"><option value="">All</option></select></label>
  <label>Status<select id="statusFilter"><option value="">All</option></select></label>
  <label>Search<input id="searchFilter" placeholder="Title, id, path"></label>
  <label class="toggle"><input id="externalFilter" type="checkbox" checked> Show external nodes</label>
  <div class="stats">
    <div class="metric"><b id="nodeCount">0</b><span>nodes</span></div>
    <div class="metric"><b id="edgeCount">0</b><span>edges</span></div>
  </div>
  <div class="legend" id="legend"></div>
  <div class="details" id="details">
    <h2>Selection</h2>
    <p>Hover or click a node.</p>
  </div>
</aside>
<section class="stage">
  <div class="toolbar">
    <button id="fitButton" type="button">Fit</button>
    <button id="modeButton" type="button">Light</button>
    <button id="motionButton" type="button">Pause</button>
    <button id="resetButton" type="button">Reset</button>
  </div>
  <svg id="graph" role="img" aria-label="Human memory graph" tabindex="0">
    <defs>
      <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
        <path d="M0,0 L0,6 L9,3 z" fill="#8792a6"></path>
      </marker>
    </defs>
    <g id="viewport"><g id="edges"></g><g id="nodes"></g></g>
  </svg>
</section>
</main>
"""


HTML_END = "</body>\n</html>\n"


def render_human_graph_html(data: dict[str, Any]) -> str:
    return (
        HTML_HEAD
        + STYLE
        + BODY
        + SCRIPT.replace("__PMEM_GRAPH_DATA__", _safe_json_script(data))
        + HTML_END
    )
