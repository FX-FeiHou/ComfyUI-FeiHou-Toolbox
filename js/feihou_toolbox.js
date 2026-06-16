import { app } from "../../scripts/app.js";

const NODE_NAME = "ManualRefCollage";
const IMAGE_COLORS = ["#4f9cff", "#ff5c5c", "#4fd36f", "#ff5cff", "#44e7e7"];
const DEFAULT_PROMPT = "person";
const DEFAULT_WIDTH = 1280;
const DEFAULT_HEIGHT = 1280;
const DEFAULT_BG = "black";
const DEFAULT_OPACITY = 0.3;
const MAX_STAGE_SIZE = 512;
const MIN_NODE_WIDTH = 420;
const MIN_NODE_HEIGHT = 260;
const MIN_DOM_HEIGHT = 48;
const MEDIA_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"];
const HELP_ICON_SIZE = 14;
const HELP_ICON_MARGIN = 4;
const CSS = `
.fh-manual-collage {
  position: relative;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 3px 3px 12px;
  color: var(--fg-color, var(--input-text, #ddd));
  user-select: none;
  pointer-events: none;
  overflow: visible;
}
.fh-manual-collage > * {
  pointer-events: auto;
}
.fh-prompt {
  width: 100%;
  min-height: 56px;
  max-height: 88px;
  resize: vertical;
  box-sizing: border-box;
  border: 1px solid var(--border-color, var(--border, #555));
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--comfy-input-bg, var(--input-bg, #222));
  color: var(--input-text, var(--fg-color, #ddd));
  outline: none;
  font: inherit;
}
.fh-load-row,
.fh-size-row {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  align-items: stretch;
  width: 100%;
}
.fh-btn {
  appearance: none;
  cursor: pointer;
  font: 12px sans-serif;
  line-height: 1.2;
  min-width: 0;
  min-height: 24px;
  padding: 4px 10px;
  color: var(--input-text, var(--fg-color, #ddd));
  background: var(--comfy-input-bg, var(--input-bg, #222));
  border: 1px solid var(--border-color, var(--border, #555));
  border-radius: 3px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.fh-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--comfy-input-bg, var(--input-bg, #222)) 88%, white 12%);
}
.fh-btn:active:not(:disabled) {
  transform: translateY(0.5px);
}
.fh-btn:disabled {
  opacity: 0.55;
  cursor: default;
}
.fh-native-widget-host {
  flex: 1 1 0;
  min-width: 0;
}
.fh-load-btn {
  width: 100%;
  min-height: 26px;
}
.fh-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: stretch;
}
.fh-stage-pane {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.fh-stage-viewport {
  flex: 1 1 auto;
  min-height: 120px;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 0 1px 1px;
  box-sizing: border-box;
  pointer-events: auto;
}
.fh-stage {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-color, var(--border, #555));
  border-radius: 8px;
  background: #000;
  box-sizing: border-box;
}
.fh-stage.white {
  background: #fff;
}
.fh-stage-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.fh-stage-bg.hidden {
  display: none;
}
.fh-stage-bg img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: fill;
}
.fh-items {
  position: absolute;
  inset: 0;
  pointer-events: none;
  contain: layout style paint;
}
.fh-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-color, #999);
  font-size: 13px;
  pointer-events: none;
}
.fh-stage.white .fh-empty {
  color: #444;
}
.fh-item {
  position: absolute;
  transform: translate(-50%, -50%);
  transform-origin: center center;
  box-sizing: border-box;
  will-change: left, top, width, height;
  pointer-events: auto;
}
.fh-item img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
}
.fh-item-box {
  position: absolute;
  inset: 0;
  border: 2px solid var(--fh-color);
  box-sizing: border-box;
  pointer-events: none;
}
.fh-item-label {
  position: absolute;
  top: -18px;
  left: 0;
  color: var(--fh-color);
  font: 13px/1 sans-serif;
  white-space: nowrap;
  text-shadow: 0 1px 1px #000;
  pointer-events: none;
}
.fh-stage.white .fh-item-label {
  text-shadow: 0 1px 1px #fff;
}
.fh-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.fh-selection-box {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid var(--fh-color, #fff);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35);
  cursor: move;
  pointer-events: auto;
}
.fh-selection-label {
  position: absolute;
  top: -18px;
  left: 0;
  color: var(--fh-color, #fff);
  font: 13px/1 sans-serif;
  white-space: nowrap;
  text-shadow: 0 1px 1px #000;
  pointer-events: none;
}
.fh-stage.white .fh-selection-label {
  text-shadow: 0 1px 1px #fff;
}
.fh-selection-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  background: var(--comfy-input-bg, #222);
  border: 2px solid var(--fh-color, #fff);
  box-sizing: border-box;
  pointer-events: auto;
}
.fh-selection-handle.tl {
  left: -6px;
  top: -6px;
  cursor: nwse-resize;
}
.fh-selection-handle.tr {
  right: -6px;
  top: -6px;
  cursor: nesw-resize;
}
.fh-selection-handle.bl {
  left: -6px;
  bottom: -6px;
  cursor: nesw-resize;
}
.fh-selection-handle.br {
  right: -6px;
  bottom: -6px;
  cursor: nwse-resize;
}
.fh-apply-btn,
.fh-reset-btn,
.fh-bg-btn {
  flex: 1 1 0;
  min-height: 26px;
}
.fh-help-panel {
  position: fixed;
  z-index: 115;
  width: 260px;
  padding: 10px 12px;
  display: none;
  line-height: 1.45;
  text-align: left;
  pointer-events: auto;
}
.fh-help-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.fh-help-item {
  margin: 0 0 6px;
}
`;

function ensureStyle() {
  if (document.getElementById("fh-manual-collage-style")) return;
  const style = document.createElement("style");
  style.id = "fh-manual-collage-style";
  style.textContent = CSS;
  document.head.appendChild(style);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function num(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function looksLikeMediaName(value) {
  if (typeof value !== "string") return false;
  const stripped = value.trim().toLowerCase();
  if (!stripped) return false;
  return MEDIA_EXTENSIONS.some((ext) => stripped.endsWith(ext) || stripped.includes(`${ext} `) || stripped.includes(`${ext}[`) || stripped.includes(`${ext}?`));
}

function hexToRgb(hex) {
  if (!hex || typeof hex !== "string") return null;
  const clean = hex.trim().replace(/^#/, "");
  if (/^[0-9a-fA-F]{3}$/.test(clean)) {
    return {
      r: parseInt(clean[0] + clean[0], 16),
      g: parseInt(clean[1] + clean[1], 16),
      b: parseInt(clean[2] + clean[2], 16),
    };
  }
  if (/^[0-9a-fA-F]{6}$/.test(clean)) {
    return {
      r: parseInt(clean.slice(0, 2), 16),
      g: parseInt(clean.slice(2, 4), 16),
      b: parseInt(clean.slice(4, 6), 16),
    };
  }
  return null;
}

function rgba(hex, alpha) {
  const rgb = hexToRgb(hex);
  if (!rgb) return `rgba(255,255,255,${alpha})`;
  return `rgba(${rgb.r},${rgb.g},${rgb.b},${alpha})`;
}

function makeDefaultItems(count, width, height) {
  if (count <= 0) return [];
  const minScale = Math.min(width / Math.max(1, height), height / Math.max(1, width));
  const scale = Math.max(0.2, Math.min(0.55, 0.38 * minScale + 0.14));
  return Array.from({ length: count }, (_, index) => ({
    x: (index + 0.5) / count,
    y: 0.72,
    scale,
    z: count - index,
  }));
}

function parseLayout(layoutJson, count, width, height, background) {
  let layout = {};
  if (typeof layoutJson === "string" && layoutJson.trim()) {
    try {
      const parsed = JSON.parse(layoutJson);
      if (parsed && typeof parsed === "object") layout = parsed;
    } catch {
      layout = {};
    }
  }
  const outWidth = clamp(Math.round(num(layout.width, width)), 64, 8192);
  const outHeight = clamp(Math.round(num(layout.height, height)), 64, 8192);
  const outBg = String(layout.background || background || DEFAULT_BG).toLowerCase() === "white" ? "white" : "black";
  const defaults = makeDefaultItems(count, outWidth, outHeight);
  const rawItems = Array.isArray(layout.items) ? layout.items : [];
  const items = defaults.map((fallback, index) => {
    const item = rawItems[index] && typeof rawItems[index] === "object" ? rawItems[index] : {};
    return {
      x: clamp(num(item.x, fallback.x), -1, 2),
      y: clamp(num(item.y, fallback.y), -1, 2),
      scale: clamp(num(item.scale, fallback.scale), 0.02, 4),
      z: Number.isFinite(Number(item.z)) ? Number(item.z) : fallback.z,
    };
  });
  return { width: outWidth, height: outHeight, background: outBg, items };
}

function syncWidgetValue(state, widget, value) {
  if (!widget) return;
  state.syncing = true;
  widget.value = value;
  if (typeof widget.callback === "function") widget.callback.call(widget, value);
  state.syncing = false;
}

function setHiddenWidget(widget) {
  if (!widget) return;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
}

function findWidget(node, name) {
  return node.widgets?.find((widget) => widget && widget.name === name) || null;
}

function hasLinkedInput(node, inputName) {
  const input = node.inputs?.find((slot) => slot && slot.name === inputName);
  return !!input?.link;
}

function getLinkedMediaName(node, inputName, visited = new Set()) {
  const input = node.inputs?.find((slot) => slot && slot.name === inputName);
  if (!input?.link) return "";
  const link = app.graph?.links?.[input.link];
  if (!link) return "";
  const sourceId = String(link.origin_id);
  if (visited.has(sourceId)) return "";
  visited.add(sourceId);
  const source = app.graph?.getNodeById?.(link.origin_id);
  if (!source) return "";

  const preferredNames = ["image", "video", "upload", "filename", "file", "path", "image_name", "video_file", "media"];
  const widgetValues = source.widgets || [];
  for (const widget of widgetValues) {
    const name = String(widget?.name || "").toLowerCase();
    if (preferredNames.includes(name) && looksLikeMediaName(widget?.value)) {
      return String(widget.value);
    }
  }
  for (const widget of widgetValues) {
    if (looksLikeMediaName(widget?.value)) {
      return String(widget.value);
    }
  }
  for (const upstream of source.inputs || []) {
    if (!upstream?.name) continue;
    const resolved = getLinkedMediaName(source, upstream.name, visited);
    if (resolved) return resolved;
  }
  return "";
}

function createButton(text, className = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `fh-btn ${className}`.trim();
  button.textContent = text;
  return button;
}

function computeNodeDomHeight(node, size) {
  const baseHeight = size?.[1] || node?.size?.[1] || MIN_NODE_HEIGHT;
  const widgetY = node?._fhDomWidget?.last_y;
  const offset = widgetY != null ? widgetY + 10 : 220;
  return Math.max(MIN_DOM_HEIGHT, Math.round(baseHeight - offset));
}

function clampNodeSize(node, size) {
  if (!node) return size || [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
  const minSize = node._fhMinSize || [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
  const target = size || node.size || [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
  const width = Math.max(target[0] || MIN_NODE_WIDTH, minSize[0] || MIN_NODE_WIDTH);
  const height = Math.max(target[1] || MIN_NODE_HEIGHT, minSize[1] || MIN_NODE_HEIGHT);
  if (size) {
    size[0] = width;
    size[1] = height;
  }
  if (node.size) {
    node.size[0] = width;
    node.size[1] = height;
  }
  return [width, height];
}

function applyNodeDomHeight(node, size) {
  if (!node?._fhDomWidget?.element) return;
  const nextSize = clampNodeSize(node, size || node.size);
  const domHeight = computeNodeDomHeight(node, nextSize);
  if (node._fhDomHeight !== domHeight) {
    node._fhDomHeight = domHeight;
    node._fhDomWidget.element.style.height = `${domHeight}px`;
  } else if (!node._fhDomWidget.element.style.height) {
    node._fhDomWidget.element.style.height = `${domHeight}px`;
  }
}

function buildManualUI(node) {
  ensureStyle();

  const layoutWidget = findWidget(node, "layout_json");
  const promptWidget = findWidget(node, "prompt");
  const widthWidget = findWidget(node, "width");
  const heightWidget = findWidget(node, "height");
  const backgroundWidget = findWidget(node, "background");
  const thresholdWidget = findWidget(node, "detection_threshold");
  const opacityWidget = findWidget(node, "background_opacity");

  for (const widget of [layoutWidget, promptWidget, backgroundWidget, thresholdWidget]) {
    setHiddenWidget(widget);
  }

  const initial = parseLayout(
    layoutWidget?.value || "",
    5,
    num(widthWidget?.value, DEFAULT_WIDTH),
    num(heightWidget?.value, DEFAULT_HEIGHT),
    backgroundWidget?.value || DEFAULT_BG
  );

  const state = {
    syncing: false,
    prompt: String(promptWidget?.value || DEFAULT_PROMPT),
    width: initial.width,
    height: initial.height,
    pendingWidth: initial.width,
    pendingHeight: initial.height,
    background: initial.background,
    initialBackground: initial.background,
    backgroundOpacity: clamp(num(opacityWidget?.value, DEFAULT_OPACITY), 0, 1),
    selected: 0,
    images: ["", "", "", "", ""],
    imageMeta: [null, null, null, null, null],
    backgroundPreview: "",
    items: initial.items.map((item) => ({ ...item })),
    stageScale: 1,
    stageW: 1,
    stageH: 1,
    loading: false,
    renderQueued: false,
    transformQueued: false,
    helpVisible: false,
  };

  const root = document.createElement("div");
  root.className = "fh-manual-collage";

  const prompt = document.createElement("textarea");
  prompt.className = "fh-prompt";
  prompt.spellcheck = false;
  prompt.value = state.prompt;

  const loadRow = document.createElement("div");
  loadRow.className = "fh-load-row";
  const loadBtn = createButton("载入图片", "fh-load-btn");
  loadRow.append(loadBtn);

  const body = document.createElement("div");
  body.className = "fh-body";

  const stagePane = document.createElement("div");
  stagePane.className = "fh-stage-pane";

  const stageViewport = document.createElement("div");
  stageViewport.className = "fh-stage-viewport";

  const stage = document.createElement("div");
  stage.className = "fh-stage";

  const backgroundLayer = document.createElement("div");
  backgroundLayer.className = "fh-stage-bg hidden";
  const backgroundImage = document.createElement("img");
  backgroundImage.alt = "video_frame";
  backgroundLayer.appendChild(backgroundImage);

  const itemsLayer = document.createElement("div");
  itemsLayer.className = "fh-items";

  const overlay = document.createElement("div");
  overlay.className = "fh-overlay";

  const selectionBox = document.createElement("div");
  selectionBox.className = "fh-selection-box";
  selectionBox.style.display = "none";

  const selectionLabel = document.createElement("div");
  selectionLabel.className = "fh-selection-label";
  selectionBox.appendChild(selectionLabel);

  for (const pos of ["tl", "tr", "bl", "br"]) {
    const handle = document.createElement("div");
    handle.className = `fh-selection-handle ${pos}`;
    handle.dataset.handle = pos;
    selectionBox.appendChild(handle);
  }
  overlay.appendChild(selectionBox);

  const empty = document.createElement("div");
  empty.className = "fh-empty";
  empty.textContent = "点击载入图片";

  stage.append(backgroundLayer, itemsLayer, overlay, empty);
  stageViewport.appendChild(stage);
  stagePane.append(stageViewport);
  body.appendChild(stagePane);

  const sizeRow = document.createElement("div");
  sizeRow.className = "fh-size-row";

  const widthHost = document.createElement("div");
  widthHost.className = "fh-native-widget-host";
  const heightHost = document.createElement("div");
  heightHost.className = "fh-native-widget-host";
  const opacityHost = document.createElement("div");
  opacityHost.className = "fh-native-widget-host";
  sizeRow.append(widthHost, heightHost, opacityHost);

  const actionRow = document.createElement("div");
  actionRow.className = "fh-size-row";
  const applyBtn = createButton("应用尺寸", "fh-apply-btn");
  const resetBtn = createButton("重置排版", "fh-reset-btn");
  const bgBtn = createButton("背景切换", "fh-bg-btn");
  actionRow.append(applyBtn, resetBtn, bgBtn);

  const helpText = document.createElement("div");
  helpText.className = "comfy-menu fh-help-panel";
  helpText.innerHTML = [
    '<div class="fh-help-title">操作方法</div>',
    '<div class="fh-help-item">1. 连好参考图，点击载入图片，节点会先抠图再放进拼图画布。</div>',
    '<div class="fh-help-item">2. 如果接了 video_frame，载入图片时会同步把视频首帧铺到背景。</div>',
    '<div class="fh-help-item">3. 单击人物即可切换当前选中图层。</div>',
    '<div class="fh-help-item">4. 拖动选中框可移动人物，拖动四角控件可缩放人物。</div>',
    '<div class="fh-help-item">5. 应用尺寸会按宽高更新画布比例，重置排版会恢复初始布局。</div>',
    '<div class="fh-help-item">6. 点击说明框内部任意位置即可关闭说明。</div>',
  ].join("");
  helpText.style.display = "none";

  const imageEls = [];
  let overlayQueued = false;

  function ensureHelpPopupHost() {
    if (helpText.parentElement !== document.body) {
      document.body.appendChild(helpText);
    }
  }

  function getHelpIconRect() {
    return {
      x: (node.size?.[0] || MIN_NODE_WIDTH) - HELP_ICON_SIZE - HELP_ICON_MARGIN,
      y: HELP_ICON_SIZE - 34,
      w: HELP_ICON_SIZE,
      h: HELP_ICON_SIZE,
    };
  }

  function hasForegroundImages() {
    return state.images.some(Boolean);
  }

  function hasStageContent() {
    return hasForegroundImages() || !!state.backgroundPreview;
  }

  function firstLoadedIndex() {
    const index = state.images.findIndex(Boolean);
    return index >= 0 ? index : 0;
  }

  function syncLayoutJson() {
    const payload = {
      width: Math.round(state.width),
      height: Math.round(state.height),
      background: state.background,
      items: state.items.map((item, index) => ({
        x: Number(clamp(item.x, -1, 2).toFixed(5)),
        y: Number(clamp(item.y, -1, 2).toFixed(5)),
        scale: Number(clamp(item.scale, 0.02, 4).toFixed(5)),
        z: Number.isFinite(item.z) ? item.z : 5 - index,
      })),
    };
    syncWidgetValue(state, layoutWidget, JSON.stringify(payload));
    syncWidgetValue(state, backgroundWidget, state.background);
  }

  function syncPrompt() {
    syncWidgetValue(state, promptWidget, state.prompt);
  }

  function syncSizeWidgets() {
    syncWidgetValue(state, widthWidget, state.width);
    syncWidgetValue(state, heightWidget, state.height);
  }

  function syncOpacityWidget() {
    syncWidgetValue(state, opacityWidget, state.backgroundOpacity);
  }

  function attachWidgetHost(widget, host, placeholder = "") {
    if (!widget || !host) return;
    const place = () => {
      const inputEl = widget.inputEl || widget.element;
      const el =
        inputEl?.closest?.(".dom-widget") ||
        inputEl?.closest?.(".comfy-widget") ||
        widget.element ||
        inputEl?.parentElement ||
        inputEl;
      if (!el) return;
      if (host.firstElementChild !== el) {
        host.replaceChildren(el);
      }
      if (el.style) {
        el.style.width = "100%";
        el.style.minWidth = "0";
        el.style.margin = "0";
        el.style.boxSizing = "border-box";
        el.style.display = "block";
      }
      if (widget.inputEl?.style) {
        widget.inputEl.style.display = "";
        widget.inputEl.style.width = "100%";
        widget.inputEl.style.minWidth = "0";
      }
      if (placeholder && "placeholder" in (widget.inputEl || {})) {
        widget.inputEl.placeholder = placeholder;
      }
    };
    place();
    requestAnimationFrame(place);
    setTimeout(place, 0);
  }

  function attachAllHosts() {
    attachWidgetHost(widthWidget, widthHost, "width");
    attachWidgetHost(heightWidget, heightHost, "height");
    attachWidgetHost(opacityWidget, opacityHost, "opacity");
  }

  function hideHelp() {
    state.helpVisible = false;
    helpText.style.display = "none";
  }

  function toggleHelp(force) {
    state.helpVisible = typeof force === "boolean" ? force : !state.helpVisible;
    helpText.style.display = state.helpVisible ? "block" : "none";
    if (state.helpVisible) {
      scheduleOverlay();
    }
  }

  function getIntrinsicDomMinSize() {
    const rootStyle = getComputedStyle(root);
    const viewportStyle = getComputedStyle(stageViewport);
    const gap = num(parseFloat(rootStyle.rowGap || rootStyle.gap || "0"), 0);
    const paddingX = num(parseFloat(rootStyle.paddingLeft || "0"), 0) + num(parseFloat(rootStyle.paddingRight || "0"), 0);
    const paddingY = num(parseFloat(rootStyle.paddingTop || "0"), 0) + num(parseFloat(rootStyle.paddingBottom || "0"), 0);
    const viewportPadX = num(parseFloat(viewportStyle.paddingLeft || "0"), 0) + num(parseFloat(viewportStyle.paddingRight || "0"), 0);
    const viewportPadY = num(parseFloat(viewportStyle.paddingTop || "0"), 0) + num(parseFloat(viewportStyle.paddingBottom || "0"), 0);
    const controlsHeight =
      Math.ceil(sizeRow.offsetHeight || 32) +
      Math.ceil(prompt.offsetHeight || 56) +
      Math.ceil(loadRow.offsetHeight || 32) +
      Math.ceil(actionRow.offsetHeight || 32);
    const bodyHeight = Math.ceil(state.stageH + viewportPadY + 2);
    const domWidth = Math.ceil(Math.max(MIN_NODE_WIDTH, state.stageW + paddingX + viewportPadX + 4));
    const domHeight = Math.ceil(paddingY + controlsHeight + bodyHeight + gap * 4 + 4);
    return [domWidth, domHeight];
  }

  function updateMinNodeSize() {
    const [domWidth, domHeight] = getIntrinsicDomMinSize();
    const widgetTop = node?._fhDomWidget?.last_y ?? 0;
    const minWidth = Math.max(MIN_NODE_WIDTH, domWidth);
    const minHeight = Math.max(MIN_NODE_HEIGHT, widgetTop + domHeight + 10);
    if (!node._fhMinSize || node._fhMinSize[0] !== minWidth || node._fhMinSize[1] !== minHeight) {
      node._fhMinSize = [minWidth, minHeight];
      node.min_size = [minWidth, minHeight];
    }
    const currentSize = node.size || [minWidth, minHeight];
    const nextWidth = Math.max(currentSize[0], minWidth);
    const nextHeight = Math.max(currentSize[1], minHeight);
    if (nextWidth !== currentSize[0] || nextHeight !== currentSize[1]) {
      if (typeof node.setSize === "function") {
        node.setSize([nextWidth, nextHeight]);
      } else {
        node.size = [nextWidth, nextHeight];
      }
      app.graph?.setDirtyCanvas?.(true, true);
    }
  }

  function scheduleOverlay() {
    if (overlayQueued) return;
    overlayQueued = true;
    requestAnimationFrame(() => {
      overlayQueued = false;
      updateHelpAnchor();
    });
  }

  function updateHelpAnchor() {
    ensureHelpPopupHost();
    if (!state.helpVisible) {
      helpText.style.display = "none";
      return;
    }
    const canvas = app.canvas?.canvas;
    const rect = canvas?.getBoundingClientRect?.();
    const ds = app.canvas?.ds;
    if (!rect || !node?.pos || !ds) {
      helpText.style.display = "none";
      return;
    }
    const scale = ds.scale || 1;
    const offset = ds.offset || [0, 0];
    const left = rect.left + (node.pos[0] + offset[0] + (node.size?.[0] || MIN_NODE_WIDTH) + 10) * scale;
    const top = rect.top + (node.pos[1] + offset[1]) * scale;
    helpText.style.display = "block";
    helpText.style.left = `${Math.round(left)}px`;
    helpText.style.top = `${Math.round(top)}px`;
  }

  function createImageItem(index) {
    const wrap = document.createElement("div");
    wrap.className = "fh-item";
    wrap.dataset.index = String(index);
    wrap.style.setProperty("--fh-color", IMAGE_COLORS[index]);

    const img = document.createElement("img");
    img.alt = `image${index + 1}`;

    const box = document.createElement("div");
    box.className = "fh-item-box";

    const label = document.createElement("div");
    label.className = "fh-item-label";
    label.textContent = `image${index + 1}`;

    wrap.append(img, box, label);
    itemsLayer.appendChild(wrap);
    imageEls[index] = { wrap, img };
  }

  for (let index = 0; index < 5; index++) {
    createImageItem(index);
    imageEls[index].wrap.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!state.images[index]) return;
      state.selected = index;
      renderSelection();
      updateButtons();
    });
  }

  resetBtn.title = "复位";
  resetBtn.addEventListener("click", (event) => {
    event.preventDefault();
    state.items = makeDefaultItems(5, state.width, state.height);
    state.selected = firstLoadedIndex();
    state.background = state.initialBackground;
    syncLayoutJson();
    renderFull();
  });
  bgBtn.title = "黑白切换";
  bgBtn.addEventListener("click", (event) => {
    event.preventDefault();
    state.background = state.background === "white" ? "black" : "white";
    syncLayoutJson();
    updateBackgroundVisual();
    updateButtons();
  });

  helpText.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    hideHelp();
  });

  const onDocumentPointerDown = (event) => {
    if (!state.helpVisible) return;
    if (helpText.contains(event.target)) return;
    hideHelp();
  };
  document.addEventListener("pointerdown", onDocumentPointerDown, true);

  function updateButtons() {
    resetBtn.disabled = !hasForegroundImages();
    loadBtn.disabled = state.loading;
    loadBtn.textContent = state.loading ? "载入中..." : "载入图片";
    stage.classList.toggle("white", state.background === "white");
    stage.style.background = state.background === "white" ? "#fff" : "#000";
    empty.style.display = hasStageContent() ? "none" : "flex";
    empty.textContent = state.loading ? "正在抠图..." : "点击载入图片";
  }

  function layoutStage() {
    const maxDim = Math.max(1, state.width, state.height);
    const scale = Math.min(MAX_STAGE_SIZE / maxDim, 1);
    const stageW = Math.max(1, Math.floor(state.width * scale));
    const stageH = Math.max(1, Math.floor(state.height * scale));
    state.stageScale = scale;
    state.stageW = stageW;
    state.stageH = stageH;
    stage.style.width = `${stageW}px`;
    stage.style.height = `${stageH}px`;
  }

  function getItemMetrics(index) {
    const item = state.items[index];
    const src = state.images[index];
    if (!item || !src) return null;
    const meta = state.imageMeta[index];
    const ratio = meta ? meta.w / Math.max(1, meta.h) : 0.42;
    const base = Math.min(state.width, state.height);
    const displayH = Math.max(12, base * item.scale * state.stageScale);
    const displayW = Math.max(12, displayH * ratio);
    const cx = item.x * state.stageW;
    const cy = item.y * state.stageH;
    return {
      displayW,
      displayH,
      cx,
      cy,
      x: cx - displayW / 2,
      y: cy - displayH / 2,
      z: item.z ?? (5 - index),
    };
  }

  function applyItemVisual(index) {
    const el = imageEls[index];
    const src = state.images[index];
    const metrics = getItemMetrics(index);
    if (!el || !src || !metrics) {
      if (el) el.wrap.style.display = "none";
      return;
    }
    el.wrap.style.display = "block";
    el.wrap.style.left = `${metrics.cx}px`;
    el.wrap.style.top = `${metrics.cy}px`;
    el.wrap.style.width = `${metrics.displayW}px`;
    el.wrap.style.height = `${metrics.displayH}px`;
    el.wrap.style.zIndex = String(metrics.z);
    if (el.img.src !== src) {
      el.img.src = src;
    }
  }

  function updateBackgroundVisual() {
    stage.classList.toggle("white", state.background === "white");
    stage.style.background = state.background === "white" ? "#fff" : "#000";
    if (state.backgroundPreview) {
      backgroundLayer.classList.remove("hidden");
      backgroundLayer.style.opacity = String(clamp(state.backgroundOpacity, 0, 1));
      if (backgroundImage.src !== state.backgroundPreview) {
        backgroundImage.src = state.backgroundPreview;
      }
    } else {
      backgroundLayer.classList.add("hidden");
      backgroundLayer.style.opacity = "0";
      backgroundImage.removeAttribute("src");
    }
  }

  function renderSelection() {
    const metrics = getItemMetrics(state.selected);
    if (!metrics) {
      selectionBox.style.display = "none";
      return;
    }
    selectionBox.style.display = "block";
    selectionBox.style.setProperty("--fh-color", IMAGE_COLORS[state.selected]);
    selectionBox.style.left = `${metrics.x}px`;
    selectionBox.style.top = `${metrics.y}px`;
    selectionBox.style.width = `${metrics.displayW}px`;
    selectionBox.style.height = `${metrics.displayH}px`;
    selectionLabel.textContent = `image${state.selected + 1}`;
  }

  function renderFull() {
    state.renderQueued = false;
    attachAllHosts();
    updateButtons();
    layoutStage();
    updateBackgroundVisual();
    for (let index = 0; index < 5; index++) {
      applyItemVisual(index);
    }
    renderSelection();
    updateMinNodeSize();
    applyNodeDomHeight(node, node.size);
    scheduleOverlay();
  }

  function scheduleRender() {
    if (state.renderQueued) return;
    state.renderQueued = true;
    requestAnimationFrame(renderFull);
  }

  function scheduleTransformVisual() {
    if (state.transformQueued) return;
    state.transformQueued = true;
    requestAnimationFrame(() => {
      state.transformQueued = false;
      applyItemVisual(state.selected);
      renderSelection();
    });
  }

  function resetPreviewState() {
    state.images = ["", "", "", "", ""];
    state.imageMeta = [null, null, null, null, null];
    state.backgroundPreview = "";
    state.selected = 0;
  }

  function updateImageMeta(src) {
    return new Promise((resolve) => {
      if (!src) {
        resolve(null);
        return;
      }
      const img = new Image();
      img.onload = () => resolve({ w: img.naturalWidth || 1, h: img.naturalHeight || 1 });
      img.onerror = () => resolve(null);
      img.src = src;
    });
  }

  async function loadImages() {
    const imageNames = [];
    let hasLinkedSource = hasLinkedInput(node, "video_frame");
    for (let index = 1; index <= 5; index++) {
      hasLinkedSource = hasLinkedSource || hasLinkedInput(node, `image_${index}`);
      imageNames.push(getLinkedMediaName(node, `image_${index}`));
    }
    const videoName = getLinkedMediaName(node, "video_frame");
    if (!hasLinkedSource) {
      resetPreviewState();
      renderFull();
      return;
    }

    state.loading = true;
    updateButtons();
    try {
      const promptData = await app.graphToPrompt?.();
      const response = await fetch("/feihou/manual_collage/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: String(node.id),
          prompt: promptData?.output || promptData || {},
          prompt_text: state.prompt,
          images: imageNames,
          video_frame: videoName,
          detection_threshold: num(thresholdWidget?.value, 0.5),
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload?.success) {
        throw new Error(payload?.error || "载入图片失败");
      }

      state.images = Array.isArray(payload.previews) ? payload.previews.slice(0, 5) : ["", "", "", "", ""];
      while (state.images.length < 5) state.images.push("");
      state.backgroundPreview = String(payload.background_preview || "");
      state.items = makeDefaultItems(5, state.width, state.height);
      state.selected = firstLoadedIndex();
      syncLayoutJson();
      state.imageMeta = await Promise.all(state.images.map((src) => updateImageMeta(src)));
      renderFull();
    } catch (error) {
      console.error(error);
      scheduleRender();
    } finally {
      state.loading = false;
      updateButtons();
    }
  }

  function beginTransform(index, event) {
    const item = state.items[index];
    if (!item || !state.images[index]) return;
    const rect = stage.getBoundingClientRect();
    const start = {
      x: event.clientX,
      y: event.clientY,
      itemX: item.x,
      itemY: item.y,
      itemScale: item.scale,
      centerX: rect.left + item.x * rect.width,
      centerY: rect.top + item.y * rect.height,
    };
    start.startDist = Math.max(1, Math.hypot(start.x - start.centerX, start.y - start.centerY));
    const resizeMode = !!event.target?.dataset?.handle;

    const move = (ev) => {
      ev.preventDefault();
      if (resizeMode) {
        const dist = Math.max(1, Math.hypot(ev.clientX - start.centerX, ev.clientY - start.centerY));
        item.scale = clamp(start.itemScale * (dist / start.startDist), 0.02, 4);
      } else {
        item.x = clamp(start.itemX + (ev.clientX - start.x) / Math.max(1, rect.width), -1, 2);
        item.y = clamp(start.itemY + (ev.clientY - start.y) / Math.max(1, rect.height), -1, 2);
      }
      state.items[index] = item;
      scheduleTransformVisual();
    };

    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      syncLayoutJson();
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  }

  loadBtn.addEventListener("click", async (event) => {
    event.preventDefault();
    await loadImages();
  });

  applyBtn.addEventListener("click", (event) => {
    event.preventDefault();
    state.pendingWidth = clamp(Math.round(num(widthWidget?.value, state.pendingWidth)), 64, 8192);
    state.pendingHeight = clamp(Math.round(num(heightWidget?.value, state.pendingHeight)), 64, 8192);
    state.width = state.pendingWidth;
    state.height = state.pendingHeight;
    syncSizeWidgets();
    syncLayoutJson();
    renderFull();
  });

  prompt.addEventListener("input", () => {
    state.prompt = prompt.value;
    syncPrompt();
  });

  selectionBox.addEventListener("pointerdown", (event) => {
    if (!state.images[state.selected]) return;
    const target = event.target;
    const box = target?.closest?.(".fh-selection-box");
    if (!box) return;
    event.preventDefault();
    event.stopPropagation();
    beginTransform(state.selected, event);
  });

  function attachWidgetSync(widget, updater) {
    if (!widget) return;
    const original = widget.callback;
    widget.callback = function (value) {
      const result = original?.apply(this, arguments);
      if (!state.syncing) updater(value);
      return result;
    };
  }

  attachWidgetSync(promptWidget, (value) => {
    state.prompt = String(value || "");
    prompt.value = state.prompt;
  });
  attachWidgetSync(widthWidget, (value) => {
    state.pendingWidth = clamp(Math.round(num(value, state.width)), 64, 8192);
  });
  attachWidgetSync(heightWidget, (value) => {
    state.pendingHeight = clamp(Math.round(num(value, state.height)), 64, 8192);
  });
  attachWidgetSync(opacityWidget, (value) => {
    state.backgroundOpacity = clamp(num(value, state.backgroundOpacity), 0, 1);
    updateBackgroundVisual();
  });
  attachWidgetSync(backgroundWidget, (value) => {
    state.background = String(value || DEFAULT_BG).toLowerCase() === "white" ? "white" : "black";
    updateBackgroundVisual();
    updateButtons();
  });
  attachWidgetSync(layoutWidget, (value) => {
    const parsed = parseLayout(value || "", 5, state.width, state.height, state.background);
    state.width = parsed.width;
    state.height = parsed.height;
    state.pendingWidth = parsed.width;
    state.pendingHeight = parsed.height;
    state.background = parsed.background;
    state.initialBackground = parsed.background;
    state.items = parsed.items;
    scheduleRender();
  });

  const resizeObserver = new ResizeObserver(() => {
    scheduleRender();
  });
  resizeObserver.observe(stageViewport);

  attachAllHosts();
  syncOpacityWidget();
  if (!layoutWidget?.value) {
    syncLayoutJson();
  }

  requestAnimationFrame(renderFull);

  node._fhManual = {
    renderFull,
    scheduleRender,
    loadImages,
    updateHelpAnchor,
    updateMinNodeSize,
    toggleHelp,
    hitHelpIcon(localPos) {
      const rect = getHelpIconRect();
      return !!localPos &&
        localPos[0] > rect.x &&
        localPos[0] < rect.x + rect.w &&
        localPos[1] > rect.y &&
        localPos[1] < rect.y + rect.h;
    },
    drawHelpIcon(ctx) {
      if (!ctx || node.flags?.collapsed) return;
      const rect = getHelpIconRect();
      ctx.save();
      ctx.translate(rect.x - 2, rect.y);
      ctx.scale(HELP_ICON_SIZE / 32, HELP_ICON_SIZE / 32);
      ctx.strokeStyle = "rgba(255,255,255,0.3)";
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.lineWidth = 2.4;
      ctx.font = "bold 36px monospace";
      ctx.fillStyle = "orange";
      ctx.fillText("?", 0, 24);
      ctx.restore();
    },
    cleanup() {
      resizeObserver.disconnect();
      document.removeEventListener("pointerdown", onDocumentPointerDown, true);
      helpText.remove();
    },
  };

  root.append(sizeRow, prompt, loadRow, actionRow, body);
  return root;
}

app.registerExtension({
  name: "FeiHou.ManualRefCollage",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    const onResize = nodeType.prototype.onResize;
    const onConfigure = nodeType.prototype.onConfigure;
    const onDrawForeground = nodeType.prototype.onDrawForeground;
    const onMouseDown = nodeType.prototype.onMouseDown;
    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    const onRemoved = nodeType.prototype.onRemoved;

    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      const ui = buildManualUI(this);
      const domWidget = this.addDOMWidget("manual_collage", "fh_manual_collage", ui, {
        serialize: false,
        hideOnZoom: false,
        margin: 0,
        getMinHeight: () => 1,
      });
      domWidget.computeSize = (width) => [width || 0, MIN_DOM_HEIGHT];
      domWidget.getHeight = () => MIN_DOM_HEIGHT;
      domWidget.getMinHeight = () => 1;
      this.resizable = true;
      this._fhDomWidget = domWidget;
      this._fhMinSize = [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
      this.size = [
        Math.max(this.size?.[0] || MIN_NODE_WIDTH, MIN_NODE_WIDTH),
        Math.max(this.size?.[1] || MIN_NODE_HEIGHT, MIN_NODE_HEIGHT),
      ];
      requestAnimationFrame(() => {
        applyNodeDomHeight(this, this.size);
        this._fhManual?.updateHelpAnchor?.();
        this._fhManual?.renderFull?.();
      });
      return result;
    };

    nodeType.prototype.onResize = function (size) {
      const result = onResize?.apply(this, arguments);
      clampNodeSize(this, size || this.size);
      applyNodeDomHeight(this, size || this.size);
      this._fhManual?.updateMinNodeSize?.();
      this._fhManual?.updateHelpAnchor?.();
      this._fhManual?.scheduleRender?.();
      return result;
    };

    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      requestAnimationFrame(() => {
        applyNodeDomHeight(this, this.size);
        this._fhManual?.updateHelpAnchor?.();
        this._fhManual?.renderFull?.();
      });
      return result;
    };

    nodeType.prototype.onDrawForeground = function (ctx) {
      const result = onDrawForeground?.apply(this, arguments);
      this._fhManual?.drawHelpIcon?.(ctx);
      if (this._fhDomWidget?.element) {
        clampNodeSize(this, this.size);
        const next = computeNodeDomHeight(this, this.size);
        if (next !== this._fhDomHeight) {
          this._fhDomHeight = next;
          this._fhDomWidget.element.style.height = `${next}px`;
          this._fhManual?.scheduleRender?.();
        }
        this._fhManual?.updateHelpAnchor?.();
      }
      return result;
    };

    nodeType.prototype.onMouseDown = function (e, localPos, canvas) {
      const result = onMouseDown?.apply(this, arguments);
      if (this._fhManual?.hitHelpIcon?.(localPos)) {
        this._fhManual?.toggleHelp?.();
        return true;
      }
      return result;
    };

    nodeType.prototype.onConnectionsChange = function () {
      const result = onConnectionsChange?.apply(this, arguments);
      requestAnimationFrame(() => this._fhManual?.renderFull?.());
      return result;
    };

    nodeType.prototype.onRemoved = function () {
      this._fhManual?.cleanup?.();
      return onRemoved?.apply(this, arguments);
    };
  },
});
