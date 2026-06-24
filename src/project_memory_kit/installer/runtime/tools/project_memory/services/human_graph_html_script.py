from __future__ import annotations


SCRIPT = """<script>
const rawData = __PMEM_GRAPH_DATA__;
const svg = document.getElementById("graph");
const viewport = document.getElementById("viewport");
const edgeLayer = document.getElementById("edges");
const nodeLayer = document.getElementById("nodes");
const filters = ["layer", "type", "status"];
const palette = { knowledge: "#2f6fed", rationale: "#8a5cf6", external: "#f2b84b", human: "#18a999" };
const requestedMode = new URLSearchParams(window.location.search).get("mode");
const state = {
  scale: 1,
  tx: 0,
  ty: 0,
  running: true,
  light: requestedMode === "light" || (!requestedMode && rawData.nodes.length > 250),
  pointer: null,
  node: null,
  hover: null
};
const nodesById = new Map(rawData.nodes.map((node, index) => [node.id, makeNode(node, index)]));
const allEdges = rawData.edges.map((edge) => ({
  ...edge,
  sourceNode: nodesById.get(edge.source),
  targetNode: nodesById.get(edge.target)
})).filter((edge) => edge.sourceNode && edge.targetNode);
for (const edge of allEdges) {
  edge.sourceNode.degree = (edge.sourceNode.degree || 0) + 1;
  edge.targetNode.degree = (edge.targetNode.degree || 0) + 1;
}
let visibleNodes = [];
let visibleEdges = [];
let adjacency = new Map();
let frame = 0;

function makeNode(node, index) {
  const angle = index * 2.399963;
  const radius = 90 + 18 * Math.sqrt(index + 1);
  return { ...node, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, vx: 0, vy: 0, degree: 0 };
}

function populateFilters() {
  for (const name of filters) {
    const select = document.getElementById(name + "Filter");
    [...new Set(rawData.nodes.map((node) => node[name]).filter(Boolean))]
      .sort()
      .forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
    select.addEventListener("change", rebuild);
  }
  document.getElementById("searchFilter").addEventListener("input", rebuild);
  document.getElementById("externalFilter").addEventListener("change", rebuild);
}

function passesFilters(node) {
  const search = document.getElementById("searchFilter").value.trim().toLowerCase();
  if (!document.getElementById("externalFilter").checked && node.layer === "external") return false;
  if (search && !`${node.title} ${node.id} ${node.path || ""}`.toLowerCase().includes(search)) return false;
  return filters.every((name) => {
    const value = document.getElementById(name + "Filter").value;
    return !value || node[name] === value;
  });
}

function rebuild() {
  visibleNodes = [...nodesById.values()].filter(passesFilters);
  const ids = new Set(visibleNodes.map((node) => node.id));
  visibleEdges = allEdges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  adjacency = buildAdjacency(visibleEdges);
  draw();
  if (!visibleNodes.length) return updateModeControls();
  if (state.light) {
    applyLightLayout();
    state.running = false;
    updateModeControls();
    updatePositions();
    fitGraph(false);
    return;
  }
  fitGraph(false);
  frame = 0;
  state.running = true;
  updateModeControls();
  requestAnimationFrame(tick);
}

function buildAdjacency(edges) {
  const map = new Map();
  for (const edge of edges) {
    if (!map.has(edge.source)) map.set(edge.source, new Set());
    if (!map.has(edge.target)) map.set(edge.target, new Set());
    map.get(edge.source).add(edge.target);
    map.get(edge.target).add(edge.source);
  }
  return map;
}

function applyLightLayout() {
  const groups = new Map();
  for (const node of visibleNodes) {
    const layer = node.layer || "unknown";
    if (!groups.has(layer)) groups.set(layer, []);
    groups.get(layer).push(node);
  }
  let ring = 0;
  for (const [, group] of groups) {
    const radius = group.length === 1 && ring === 0 ? 0 : 85 + ring * 140;
    const offset = ring * 0.47;
    group.forEach((node, index) => {
      const angle = offset + (Math.PI * 2 * index) / Math.max(group.length, 1);
      node.x = Math.cos(angle) * radius;
      node.y = Math.sin(angle) * radius;
      node.vx = 0;
      node.vy = 0;
      node.fixed = false;
    });
    ring += 1;
  }
}

function draw() {
  edgeLayer.textContent = "";
  nodeLayer.textContent = "";
  if (!visibleNodes.length) return drawEmpty();
  for (const edge of visibleEdges) edge.el = makeEdge(edge);
  for (const node of visibleNodes) node.el = makeNodeElement(node);
  updateSummary();
  updatePositions();
}

function makeEdge(edge) {
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.classList.add("edge");
  if (edge.relation === "evidence") line.classList.add("evidence");
  line.setAttribute("marker-end", "url(#arrow)");
  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = edge.relation;
  line.appendChild(title);
  edgeLayer.appendChild(line);
  return line;
}

function makeNodeElement(node) {
  const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
  group.classList.add("node", node.layer || "unknown");
  group.setAttribute("tabindex", "0");
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("r", nodeRadius(node));
  circle.setAttribute("fill", palette[node.layer] || "#18a999");
  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", nodeRadius(node) + 7);
  label.setAttribute("y", 4);
  label.textContent = node.title || node.id;
  group.append(circle, label);
  group.addEventListener("pointerdown", (event) => startNodeDrag(event, node));
  group.addEventListener("pointerenter", () => setHover(node));
  group.addEventListener("pointerleave", () => setHover(null));
  group.addEventListener("click", () => showDetails(node));
  nodeLayer.appendChild(group);
  return group;
}

function drawEmpty() {
  const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
  text.classList.add("empty");
  text.setAttribute("x", 36);
  text.setAttribute("y", 48);
  text.textContent = "No nodes match the current filters.";
  nodeLayer.appendChild(text);
  updateSummary();
}

function nodeRadius(node) {
  return Math.max(6, Math.min(18, 6 + Math.sqrt(node.degree || 0) * 2.8));
}

function tick() {
  if (!state.running || state.light) return;
  frame += 1;
  applyForces();
  updatePositions();
  if (frame < 900) requestAnimationFrame(tick);
}

function applyForces() {
  const linkDistance = 130;
  for (const edge of visibleEdges) {
    const a = edge.sourceNode, b = edge.targetNode;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.hypot(dx, dy) || 1;
    const force = (dist - linkDistance) * 0.0035;
    const fx = dx / dist * force, fy = dy / dist * force;
    if (!a.fixed) { a.vx += fx; a.vy += fy; }
    if (!b.fixed) { b.vx -= fx; b.vy -= fy; }
  }
  for (let i = 0; i < visibleNodes.length; i++) {
    const a = visibleNodes[i];
    for (let j = i + 1; j < visibleNodes.length; j++) repel(a, visibleNodes[j]);
    if (!a.fixed) {
      a.vx += -a.x * 0.0009;
      a.vy += -a.y * 0.0009;
      a.vx *= 0.86;
      a.vy *= 0.86;
      a.x += a.vx;
      a.y += a.vy;
    }
  }
}

function repel(a, b) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const dist2 = Math.max(80, dx * dx + dy * dy);
  const force = Math.min(2.8, 460 / dist2);
  const dist = Math.sqrt(dist2);
  const fx = dx / dist * force, fy = dy / dist * force;
  if (!a.fixed) { a.vx -= fx; a.vy -= fy; }
  if (!b.fixed) { b.vx += fx; b.vy += fy; }
}

function updatePositions() {
  for (const edge of visibleEdges) {
    edge.el.setAttribute("x1", edge.sourceNode.x);
    edge.el.setAttribute("y1", edge.sourceNode.y);
    edge.el.setAttribute("x2", edge.targetNode.x);
    edge.el.setAttribute("y2", edge.targetNode.y);
  }
  for (const node of visibleNodes) node.el.setAttribute("transform", `translate(${node.x},${node.y})`);
}

function fitGraph(animate = true) {
  if (!visibleNodes.length) return;
  const box = bounds();
  const width = svg.clientWidth || 900, height = svg.clientHeight || 600;
  const scale = Math.min(2.4, Math.max(0.25, Math.min(width / box.w, height / box.h) * 0.82));
  state.scale = scale;
  state.tx = width / 2 - (box.x + box.w / 2) * scale;
  state.ty = height / 2 - (box.y + box.h / 2) * scale;
  applyTransform(animate);
}

function bounds() {
  const xs = visibleNodes.map((node) => node.x);
  const ys = visibleNodes.map((node) => node.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  return { x: minX - 80, y: minY - 80, w: Math.max(160, maxX - minX + 160), h: Math.max(160, maxY - minY + 160) };
}

function applyTransform(animate = false) {
  viewport.style.transition = animate ? "transform 220ms ease" : "";
  viewport.setAttribute("transform", `translate(${state.tx},${state.ty}) scale(${state.scale})`);
}

function setHover(node) {
  state.hover = node;
  if (node) showDetails(node);
  const related = node ? adjacency.get(node.id) || new Set() : null;
  for (const item of visibleNodes) {
    const active = node && (item.id === node.id || related.has(item.id));
    item.el.classList.toggle("dim", Boolean(node && !active));
    item.el.classList.toggle("active", Boolean(active));
  }
  for (const edge of visibleEdges) {
    const active = node && (edge.source === node.id || edge.target === node.id);
    edge.el.classList.toggle("dim", Boolean(node && !active));
    edge.el.classList.toggle("active", Boolean(active));
  }
}

function showDetails(node) {
  const neighbors = adjacency.get(node.id)?.size || 0;
  document.getElementById("details").innerHTML =
    `<h2>${escapeHtml(node.title || node.id)}</h2>` +
    `<p><b>${escapeHtml(node.layer || "unknown")}</b> / ${escapeHtml(node.type || "unknown")}</p>` +
    `<p>${escapeHtml(node.id)}</p>` +
    `<p>${neighbors} connected node${neighbors === 1 ? "" : "s"}</p>` +
    (node.path ? `<p>${escapeHtml(node.path)}</p>` : "");
}

function updateSummary() {
  const mode = state.light ? "Light" : "Force";
  document.getElementById("nodeCount").textContent = visibleNodes.length;
  document.getElementById("edgeCount").textContent = visibleEdges.length;
  document.getElementById("headerSummary").textContent = `${mode} / ${visibleNodes.length} nodes / ${visibleEdges.length} edges`;
  document.getElementById("legend").innerHTML = Object.entries(palette)
    .filter(([layer]) => rawData.nodes.some((node) => node.layer === layer))
    .map(([layer, color]) => `<div class="legend-item"><span class="dot" style="background:${color}"></span>${layer}</div>`)
    .join("");
}

function updateModeControls() {
  const motion = document.getElementById("motionButton");
  document.getElementById("modeButton").textContent = state.light ? "Force" : "Light";
  motion.disabled = state.light;
  motion.textContent = state.light ? "Paused" : state.running ? "Pause" : "Run";
  updateSummary();
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}

function startNodeDrag(event, node) {
  event.stopPropagation();
  state.node = node;
  node.fixed = true;
  moveNode(event);
  svg.setPointerCapture(event.pointerId);
}

function moveNode(event) {
  const point = toWorld(event);
  state.node.x = point.x;
  state.node.y = point.y;
  state.node.vx = 0;
  state.node.vy = 0;
  updatePositions();
}

function toWorld(event) {
  const rect = svg.getBoundingClientRect();
  return { x: (event.clientX - rect.left - state.tx) / state.scale, y: (event.clientY - rect.top - state.ty) / state.scale };
}

svg.addEventListener("pointerdown", (event) => {
  if (event.target.closest(".node")) return;
  state.pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, tx: state.tx, ty: state.ty };
  svg.setPointerCapture(event.pointerId);
});
svg.addEventListener("pointermove", (event) => {
  if (state.node) return moveNode(event);
  if (!state.pointer) return;
  state.tx = state.pointer.tx + event.clientX - state.pointer.x;
  state.ty = state.pointer.ty + event.clientY - state.pointer.y;
  applyTransform();
});
svg.addEventListener("pointerup", () => { state.pointer = null; state.node = null; });
svg.addEventListener("pointercancel", () => { state.pointer = null; state.node = null; });
svg.addEventListener("wheel", (event) => {
  event.preventDefault();
  const rect = svg.getBoundingClientRect();
  const before = { x: (event.clientX - rect.left - state.tx) / state.scale, y: (event.clientY - rect.top - state.ty) / state.scale };
  state.scale = Math.max(0.18, Math.min(4, state.scale * Math.exp(-event.deltaY * 0.001)));
  state.tx = event.clientX - rect.left - before.x * state.scale;
  state.ty = event.clientY - rect.top - before.y * state.scale;
  applyTransform();
}, { passive: false });
svg.addEventListener("keydown", (event) => {
  if (event.key === "+" || event.key === "=") state.scale = Math.min(4, state.scale * 1.15);
  else if (event.key === "-") state.scale = Math.max(0.18, state.scale / 1.15);
  else if (event.key === "ArrowLeft") state.tx += event.shiftKey ? 60 : 24;
  else if (event.key === "ArrowRight") state.tx -= event.shiftKey ? 60 : 24;
  else if (event.key === "ArrowUp") state.ty += event.shiftKey ? 60 : 24;
  else if (event.key === "ArrowDown") state.ty -= event.shiftKey ? 60 : 24;
  else return;
  event.preventDefault();
  applyTransform();
});

document.getElementById("fitButton").addEventListener("click", () => fitGraph(true));
document.getElementById("modeButton").addEventListener("click", () => {
  state.light = !state.light;
  rebuild();
});
document.getElementById("resetButton").addEventListener("click", () => {
  for (const [index, node] of [...nodesById.values()].entries()) Object.assign(node, makeNode(node, index), { fixed: false });
  rebuild();
});
document.getElementById("motionButton").addEventListener("click", (event) => {
  if (state.light) return;
  state.running = !state.running;
  event.currentTarget.textContent = state.running ? "Pause" : "Run";
  if (state.running) requestAnimationFrame(tick);
});
window.addEventListener("resize", () => fitGraph(false));
populateFilters();
rebuild();
</script>
"""
