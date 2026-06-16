import { app } from "../../scripts/app.js";

const NODE_NAME = "FastGroupsBypassSwitch";
const MODE_ENABLE = LiteGraph.ALWAYS ?? 0;
const MODE_BYPASS = 4;
const MIN_NODE_WIDTH = 430;
const PROP_GROUP_1 = "fh_group_1_name";
const PROP_GROUP_2 = "fh_group_2_name";
const PROP_SELECTED = "fh_selected_group";
const ALLOWED_INPUTS = new Set(["input1", "input2"]);
const ROW_WIDGET_HEIGHT = LiteGraph.NODE_WIDGET_HEIGHT || 20;

function num(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function measureText(ctx, str) {
  return ctx.measureText(String(str ?? "")).width;
}

function fitString(ctx, value, maxWidth) {
  const text = String(value ?? "");
  if (maxWidth <= 0 || measureText(ctx, text) <= maxWidth) return text;
  const ellipsis = "...";
  const ellipsisWidth = measureText(ctx, ellipsis);
  if (ellipsisWidth >= maxWidth) return "";

  let low = 0;
  let high = text.length;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (measureText(ctx, text.slice(0, mid)) <= maxWidth - ellipsisWidth) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return text.slice(0, Math.max(0, high)) + ellipsis;
}

function roundRect(ctx, x, y, width, height, radius) {
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(x, y, width, height, [radius]);
    return;
  }
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
}

function isLowQuality() {
  return ((app.canvas?.ds?.scale || 1) <= 0.5);
}

function drawNodeWidget(ctx, options) {
  const lowQuality = isLowQuality();
  const data = {
    width: options.size[0],
    height: options.size[1],
    posY: options.pos[1],
    lowQuality,
    margin: 15,
    colorOutline: LiteGraph.WIDGET_OUTLINE_COLOR,
    colorBackground: LiteGraph.WIDGET_BGCOLOR,
    colorText: LiteGraph.WIDGET_TEXT_COLOR,
    colorTextSecondary: LiteGraph.WIDGET_SECONDARY_TEXT_COLOR,
  };
  ctx.strokeStyle = options.colorStroke || data.colorOutline;
  ctx.fillStyle = options.colorBackground || data.colorBackground;
  ctx.beginPath();
  roundRect(
    ctx,
    data.margin,
    data.posY,
    data.width - data.margin * 2,
    data.height,
    lowQuality ? 0 : options.borderRadius ?? options.size[1] * 0.5,
  );
  ctx.fill();
  if (!lowQuality) ctx.stroke();
  return data;
}

function getAllGroups(graph) {
  if (!graph) return [];
  const seenGraphs = new Set();
  const queue = [graph];
  const groups = [];
  while (queue.length) {
    const current = queue.shift();
    if (!current || seenGraphs.has(current)) continue;
    seenGraphs.add(current);
    groups.push(...(current._groups || []));
    for (const node of current.nodes || []) {
      if (node?.subgraph && !seenGraphs.has(node.subgraph)) {
        queue.push(node.subgraph);
      }
    }
  }
  return groups;
}

function findGroupByTitle(node, title) {
  const wanted = String(title || "").trim();
  if (!wanted) return null;
  const graphs = [node.graph, app.canvas?.graph, app.graph].filter(Boolean);
  const groups = [];
  for (const graph of graphs) groups.push(...getAllGroups(graph));

  const exact = groups.find((group) => String(group?.title || "").trim() === wanted);
  if (exact) return exact;

  const lowerWanted = wanted.toLowerCase();
  return groups.find((group) => String(group?.title || "").trim().toLowerCase() === lowerWanted) || null;
}

function getGroupNodes(group, selfId) {
  group?.recomputeInsideNodes?.();
  const children = group?._children ? Array.from(group._children) : Array.isArray(group?.nodes) ? group.nodes : [];
  return children.filter((child) => child && typeof child.mode === "number" && child.id !== selfId);
}

function changeModeOfNodes(nodes, mode) {
  const stack = Array.isArray(nodes) ? [...nodes] : [nodes];
  const seen = new Set();
  while (stack.length) {
    const node = stack.pop();
    if (!node || seen.has(node)) continue;
    seen.add(node);
    node.mode = mode;
    if (node.isSubgraphNode?.() && node.subgraph?.nodes?.length) {
      stack.push(...node.subgraph.nodes);
    }
  }
}

function centerOnGroup(group) {
  const canvas = app.canvas;
  if (!canvas || !group) return;
  canvas.centerOnNode(group);
  const zoomCurrent = canvas.ds?.scale || 1;
  const zoomX = canvas.canvas.width / group._size[0] - 0.02;
  const zoomY = canvas.canvas.height / group._size[1] - 0.02;
  canvas.setZoom(Math.min(zoomCurrent, zoomX, zoomY), [canvas.canvas.width / 2, canvas.canvas.height / 2]);
  canvas.setDirty(true, true);
}

function normalizeInputSlots(node) {
  if (!Array.isArray(node?.inputs)) return;
  const existingInput1 = node.inputs.find((input) => input?.name === "input1");
  const existingInput2 = node.inputs.find((input) => input?.name === "input2");
  const oldInput1 = node.inputs.find((input) => input?.name === "group_1_input");
  const oldInput2 = node.inputs.find((input) => input?.name === "group_2_input");
  if (oldInput1 && (oldInput1.link != null || !existingInput1)) oldInput1.name = "input1";
  if (oldInput2 && (oldInput2.link != null || !existingInput2)) oldInput2.name = "input2";

  const seenAllowed = new Set();
  for (let index = node.inputs.length - 1; index >= 0; index--) {
    const input = node.inputs[index];
    if (ALLOWED_INPUTS.has(input?.name) && !seenAllowed.has(input.name)) {
      seenAllowed.add(input.name);
      continue;
    }
    if (typeof node.removeInput === "function") node.removeInput(index);
    else node.inputs.splice(index, 1);
  }
  app.graph?.setDirtyCanvas?.(true, true);
}

function ensureProperties(node) {
  node.properties ??= {};
  if (node.properties[PROP_SELECTED] == null) node.properties[PROP_SELECTED] = 1;
  if (node.properties[PROP_GROUP_1] == null) node.properties[PROP_GROUP_1] = "";
  if (node.properties[PROP_GROUP_2] == null) node.properties[PROP_GROUP_2] = "";
}

function getSelected(node) {
  return num(node.properties?.[PROP_SELECTED], 1) === 2 ? 2 : 1;
}

function setSelected(node, index) {
  ensureProperties(node);
  node.properties[PROP_SELECTED] = index === 2 ? 2 : 1;
}

function getGroupName(node, index) {
  ensureProperties(node);
  const prop = index === 2 ? PROP_GROUP_2 : PROP_GROUP_1;
  return String(node.properties[prop] || "");
}

function setGroupName(node, index, value) {
  ensureProperties(node);
  const prop = index === 2 ? PROP_GROUP_2 : PROP_GROUP_1;
  node.properties[prop] = String(value ?? "");
}

function applyModes(node) {
  ensureProperties(node);
  const selected = getSelected(node);
  for (const index of [1, 2]) {
    const group = findGroupByTitle(node, getGroupName(node, index));
    if (!group) continue;
    const mode = index === selected ? MODE_ENABLE : MODE_BYPASS;
    changeModeOfNodes(getGroupNodes(group, node.id), mode);
    group.rgthree_hasAnyActiveNode = index === selected;
    group.graph?.setDirtyCanvas?.(true, false);
  }
  app.graph?.setDirtyCanvas?.(true, true);
}

class FastGroupSwitchRowWidget {
  constructor(index) {
    this.type = "custom";
    this.name = `fh_group_${index}`;
    this.label = "";
    this.value = {};
    this.options = { serialize: false };
    this.index = index;
    this.y = 0;
    this.last_y = 0;
    this.hitAreas = {};
  }

  computeSize(width) {
    return [width, ROW_WIDGET_HEIGHT];
  }

  serializeValue() {
    return undefined;
  }

  draw(ctx, node, width, posY, height) {
    this.y = posY;
    this.last_y = posY;
    const widgetData = drawNodeWidget(ctx, { size: [width, height], pos: [15, posY] });
    const selected = getSelected(node) === this.index;
    const groupName = getGroupName(node, this.index).trim();
    const fallbackName = `Group${this.index}`;
    const label = `Enable ${groupName || fallbackName}`;
    const midY = widgetData.posY + widgetData.height * 0.5;
    const margin = widgetData.margin;
    let currentX = widgetData.width - margin;
    this.hitAreas = {
      row: [margin, posY, widgetData.width - margin * 2, height],
      name: [margin + 10, posY, Math.max(60, widgetData.width - 150), height],
      nav: [widgetData.width - margin - 29, posY, 29, height],
    };

    if (!widgetData.lowQuality) {
      currentX -= 7;
      ctx.fillStyle = ctx.strokeStyle = "#89A";
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      const arrow = new Path2D(`M${currentX} ${midY} l -7 6 v -3 h -7 v -6 h 7 v -3 z`);
      ctx.fill(arrow);
      ctx.stroke(arrow);
      currentX -= 14;
      currentX -= 7;
      ctx.strokeStyle = widgetData.colorOutline;
      ctx.stroke(new Path2D(`M ${currentX} ${widgetData.posY} v ${widgetData.height}`));
    } else {
      currentX -= 28;
    }

    currentX -= 7;
    ctx.fillStyle = selected ? "#89A" : "#333";
    ctx.beginPath();
    const toggleRadius = height * 0.36;
    ctx.arc(currentX - toggleRadius, posY + height * 0.5, toggleRadius, 0, Math.PI * 2);
    ctx.fill();
    currentX -= toggleRadius * 2;

    if (!widgetData.lowQuality) {
      currentX -= 4;
      ctx.textBaseline = "alphabetic";
      ctx.textAlign = "right";
      ctx.fillStyle = selected ? widgetData.colorText : widgetData.colorTextSecondary;
      ctx.fillText(selected ? "yes" : "no", currentX, posY + height * 0.7);
      currentX -= Math.max(measureText(ctx, "yes"), measureText(ctx, "no"));
      currentX -= 7;
      ctx.textAlign = "left";
      const maxLabelWidth = currentX - (margin + 10);
      ctx.fillStyle = selected ? widgetData.colorText : widgetData.colorTextSecondary;
      ctx.fillText(fitString(ctx, label, maxLabelWidth), margin + 10, posY + height * 0.7);
    }
  }

  mouse(event, pos, node) {
    if (event.type !== "pointerdown") return false;
    const [x, y] = pos;
    const nav = this.hitAreas.nav || [];
    const name = this.hitAreas.name || [];
    if (x >= nav[0] && x <= nav[0] + nav[2] && y >= nav[1] && y <= nav[1] + nav[3]) {
      centerOnGroup(findGroupByTitle(node, getGroupName(node, this.index)));
      return true;
    }
    if (x >= name[0] && x <= name[0] + name[2] && y >= name[1] && y <= name[1] + name[3]) {
      this.promptForName(event, node);
      return true;
    }
    setSelected(node, this.index);
    applyModes(node);
    node.setDirtyCanvas?.(true, true);
    return true;
  }

  promptForName(event, node) {
    const currentValue = getGroupName(node, this.index);
    const updateValue = (value) => {
      if (value == null) return;
      setGroupName(node, this.index, value);
      applyModes(node);
      node.setDirtyCanvas?.(true, true);
    };
    if (app.canvas?.prompt) {
      app.canvas.prompt(`Group${this.index} title`, currentValue, updateValue, event);
      return;
    }
    const value = prompt(`Group${this.index} title`, currentValue);
    updateValue(value);
  }
}

function addCustomWidget(node, widget) {
  if (typeof node.addCustomWidget === "function") return node.addCustomWidget(widget);
  node.widgets ??= [];
  node.widgets.push(widget);
  return widget;
}

function removeOldUiWidgets(node) {
  if (!Array.isArray(node.widgets)) return;
  for (let index = node.widgets.length - 1; index >= 0; index--) {
    const widget = node.widgets[index];
    if (
      widget?.name === "fh_fast_groups_bypass_switch" ||
      widget?.name === "fast_groups_bypass_switch" ||
      widget?.name === "fh_group_1" ||
      widget?.name === "fh_group_2"
    ) {
      if (typeof node.removeWidget === "function") node.removeWidget(index);
      else node.widgets.splice(index, 1);
    }
  }
}

function setupNodeUi(node) {
  ensureProperties(node);
  normalizeInputSlots(node);
  removeOldUiWidgets(node);
  addCustomWidget(node, new FastGroupSwitchRowWidget(1));
  addCustomWidget(node, new FastGroupSwitchRowWidget(2));
  node._fhFastGroupsBypassSwitch = {
    applyModes: () => applyModes(node),
    refresh: () => {
      normalizeInputSlots(node);
      node.setDirtyCanvas?.(true, true);
    },
  };
  node.size = [
    Math.max(node.size?.[0] || MIN_NODE_WIDTH, MIN_NODE_WIDTH),
    Math.max(node.size?.[1] || 1, node.computeSize?.()[1] || 1),
  ];
  node.resizable = true;
  requestAnimationFrame(() => applyModes(node));
}

app.registerExtension({
  name: "FeiHou.FastGroupsBypassSwitch",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    const onConfigure = nodeType.prototype.onConfigure;
    const onConnectionsChange = nodeType.prototype.onConnectionsChange;

    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      setupNodeUi(this);
      return result;
    };

    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      requestAnimationFrame(() => {
        setupNodeUi(this);
        this._fhFastGroupsBypassSwitch?.applyModes?.();
      });
      return result;
    };

    nodeType.prototype.onConnectionsChange = function () {
      const result = onConnectionsChange?.apply(this, arguments);
      requestAnimationFrame(() => this._fhFastGroupsBypassSwitch?.refresh?.());
      return result;
    };
  },
});
