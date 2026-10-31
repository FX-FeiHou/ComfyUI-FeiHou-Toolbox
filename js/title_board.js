import { app } from "../../scripts/app.js";

// Displays the title boards saved by the NB-ComfyUI launcher: built-in Note nodes
// whose style is stored in properties.nb_title_board. Display only; when the
// launcher is present its own title boards handle these nodes instead.

const NOTE_TYPE = "Note";
const BOARD_KEY = "nb_title_board";
const NB_EXTENSION = "NB.LayoutTools";
const TEXT_CLASS = "feihou-title-board-text";
const STYLE_ID = "feihou-title-board-style";
const TRANSPARENT = "rgba(0, 0, 0, 0)";

// Values must match what the launcher saves, or boards would look different here.
const EFFECTS = {
  solid: {},
  gold: { dir: "v", stops: [[0, "#fff8d6"], [0.32, "#f6d36b"], [0.5, "#b5832a"], [0.62, "#f2d27c"], [1, "#94600f"]], outline: "#3a2406", shadow: true },
  champagne: { dir: "v", stops: [[0, "#fffaf0"], [0.35, "#efd9b4"], [0.52, "#b8916a"], [0.65, "#f3e2c4"], [1, "#9c7650"]], outline: "#3b2a1a", shadow: true },
  rosegold: { dir: "v", stops: [[0, "#fff1ec"], [0.35, "#f4bfb1"], [0.52, "#c07a6a"], [0.65, "#f6cfc3"], [1, "#9a5a4c"]], outline: "#3d1f19", shadow: true },
  silver: { dir: "v", stops: [[0, "#ffffff"], [0.35, "#dfe3e8"], [0.5, "#8b939d"], [0.62, "#e9ecf0"], [1, "#6c747e"]], outline: "#1d2228", shadow: true },
  bronze: { dir: "v", stops: [[0, "#ffe1bf"], [0.35, "#d9955a"], [0.52, "#7d4a1e"], [0.65, "#e0a46c"], [1, "#5e3412"]], outline: "#2a1606", shadow: true },
  aurora: { dir: "h", stops: [[0, "#6ff7e8"], [0.5, "#8b7bff"], [1, "#ff74d4"]], shadow: true },
  sunset: { dir: "h", stops: [[0, "#ffd36e"], [0.5, "#ff7a59"], [1, "#c94bff"]], shadow: true },
  neon: { dir: "h", stops: [[0, "#ff5fd7"], [1, "#5fe3ff"]], glow: "#ff5fd7" },
  ice: { dir: "v", stops: [[0, "#f2fdff"], [0.45, "#9be3ff"], [1, "#2f7bd8"]], outline: "#0b2a4a", shadow: true },
  jade: { dir: "v", stops: [[0, "#effff0"], [0.45, "#6fe0a0"], [1, "#0e7a52"]], outline: "#06301f", shadow: true },
};

const FONTS = {
  yahei: '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif',
  heiti: 'SimHei, "Heiti SC", "PingFang SC", sans-serif',
  songti: 'SimSun, "Songti SC", serif',
  kaiti: 'KaiTi, STKaiti, "Kaiti SC", serif',
  fangsong: "FangSong, STFangsong, serif",
};

let broken = false;

function isBoard(node) {
  return node?.type === NOTE_TYPE && Boolean(node.properties?.[BOARD_KEY]);
}

function textWidget(node) {
  return node.widgets?.find((widget) => widget.name === "text");
}

function readSettings(node) {
  const saved = node.properties[BOARD_KEY];
  const size = Number(saved.fontSize);
  return {
    lines: String(textWidget(node)?.value ?? node.properties.text ?? "").replace(/\r/g, "").replace(/\n+$/, "").split("\n"),
    fontSize: Number.isFinite(size) ? Math.min(400, Math.max(8, size)) : 48,
    fontColor: String(saved.fontColor || "#ffffff"),
    background: String(saved.background ?? ""),
    align: ["left", "center", "right"].includes(saved.align) ? saved.align : "left",
    bold: saved.bold == null ? true : Boolean(saved.bold),
    italic: Boolean(saved.italic),
    font: FONTS[saved.font] || FONTS.yahei,
    outline: Boolean(saved.outline),
    shadow: Boolean(saved.shadow),
    effect: EFFECTS[saved.effect] || EFFECTS.solid,
  };
}

// Light text gets a dark outline and dark text a light one.
function contrastColor(color) {
  let hex = /^#([0-9a-f]{3,8})$/i.exec(color)?.[1];
  if (!hex) return "#000000";
  if (hex.length < 6) hex = [...hex.slice(0, 3)].map((char) => char + char).join("");
  const [r, g, b] = [0, 2, 4].map((at) => parseInt(hex.slice(at, at + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 140 ? "#1a1a1a" : "#ffffff";
}

function setShadow(ctx, color, blur, offset) {
  ctx.shadowColor = color;
  ctx.shadowBlur = blur;
  ctx.shadowOffsetX = offset;
  ctx.shadowOffsetY = offset;
}

function paintBoard(node, ctx) {
  const settings = readSettings(node);
  const { effect, fontSize, lines, align } = settings;
  const outline = settings.outline || Boolean(effect.outline);
  const shadow = settings.shadow || Boolean(effect.shadow);

  ctx.font = `${settings.italic ? "italic " : ""}${settings.bold ? "bold " : ""}${fontSize}px ${settings.font}`;
  const extra = (outline ? 0.08 : 0) + (shadow ? 0.08 : 0) + (effect.glow ? 0.25 : 0);
  const padding = Math.round(fontSize * ((settings.background ? 0.35 : 0.1) + extra));
  const lineHeight = fontSize * 1.25;
  const textWidth = Math.max(40, ...lines.map((line) => ctx.measureText(line || " ").width));
  const width = Math.ceil(textWidth + (settings.italic ? fontSize * 0.15 : 0) + padding * 2);
  const height = Math.ceil(lines.length * lineHeight + padding * 2);
  if (Math.abs(node.size[0] - width) > 0.5 || Math.abs(node.size[1] - height) > 0.5) {
    node.setSize([width, height]);
  }

  if (settings.background) {
    ctx.fillStyle = settings.background;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(0, 0, width, height, Math.round(fontSize * 0.2));
    else ctx.rect(0, 0, width, height);
    ctx.fill();
  }

  ctx.textBaseline = "middle";
  ctx.textAlign = align;
  const x = align === "center" ? width / 2 : align === "right" ? width - padding : padding;
  const lineY = (index) => padding + lineHeight * (index + 0.5);

  const fillFor = (line, index) => {
    if (!effect.stops) return settings.fontColor;
    let gradient;
    if (effect.dir === "h") {
      const lineWidth = ctx.measureText(line).width;
      const left = align === "center" ? x - lineWidth / 2 : align === "right" ? x - lineWidth : x;
      gradient = ctx.createLinearGradient(left, 0, left + lineWidth, 0);
    } else {
      const top = lineY(index) - fontSize / 2;
      gradient = ctx.createLinearGradient(0, top, 0, top + fontSize);
    }
    for (const [at, color] of effect.stops) gradient.addColorStop(at, color);
    return gradient;
  };

  // The drop shadow is cast once: by the outline when there is one, otherwise by the fill.
  const dropShadow = (on) => setShadow(ctx, on ? "rgba(0, 0, 0, 0.6)" : "transparent", on ? fontSize * 0.12 : 0, on ? fontSize * 0.06 : 0);
  if (outline) {
    dropShadow(shadow);
    ctx.lineJoin = "round";
    ctx.lineWidth = Math.max(1.5, fontSize * (settings.outline ? 0.12 : 0.05));
    ctx.strokeStyle = effect.outline || contrastColor(settings.fontColor);
    lines.forEach((line, index) => ctx.strokeText(line, x, lineY(index)));
  }
  dropShadow(shadow && !outline);
  if (effect.glow) setShadow(ctx, effect.glow, fontSize * 0.4, 0);
  lines.forEach((line, index) => {
    ctx.fillStyle = fillFor(line, index);
    ctx.fillText(line, x, lineY(index));
  });
}

function decorate(node) {
  if (node.feihouTitleBoardReady) return;
  node.feihouTitleBoardReady = true;
  const fixed = (key, value) => Object.defineProperty(node, key, { configurable: true, get: value, set: () => {} });
  fixed("title_mode", () => window.LiteGraph?.NO_TITLE ?? 1);
  fixed("renderingColor", () => TRANSPARENT);
  fixed("renderingBgColor", () => TRANSPARENT);
  node.resizable = false;
  const widget = textWidget(node);
  if (widget?.visibility?.surfaces) widget.visibility.surfaces.canvas = "never";
  widget?.element?.classList?.add(TEXT_CLASS);
  widget?.inputEl?.classList?.add(TEXT_CLASS);
}

// Falls back to an ordinary note so the text stays readable.
function undecorate(node) {
  if (!node.feihouTitleBoardReady) return;
  node.feihouTitleBoardReady = false;
  for (const key of ["title_mode", "renderingColor", "renderingBgColor"]) delete node[key];
  node.resizable = true;
  const widget = textWidget(node);
  if (widget?.visibility?.surfaces) widget.visibility.surfaces.canvas = "shown";
  widget?.element?.classList?.remove(TEXT_CLASS);
  widget?.inputEl?.classList?.remove(TEXT_CLASS);
  node.setDirtyCanvas?.(true, true);
}

function install() {
  const proto = window.LiteGraph?.registered_node_types?.[NOTE_TYPE]?.prototype;
  if (!proto) return;

  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement("style");
    style.id = STYLE_ID;
    // Vue nodes never call the canvas drawing, so they keep showing the text box.
    style.textContent = `.${TEXT_CLASS} { display: none !important; } .lg-node .${TEXT_CLASS} { display: block !important; }`;
    document.head.append(style);
  }

  const onDrawForeground = proto.onDrawForeground;
  proto.onDrawForeground = function (ctx, ...rest) {
    if (!isBoard(this) || broken) {
      if (isBoard(this)) undecorate(this);
      return onDrawForeground?.call(this, ctx, ...rest);
    }
    ctx.save();
    try {
      decorate(this);
      paintBoard(this, ctx);
    } catch (error) {
      broken = true;
      console.warn("[FeiHou Toolbox] title board drawing failed, showing plain notes", error);
    } finally {
      ctx.restore();
    }
  };
}

app.registerExtension({
  name: "FeiHou.TitleBoard",
  setup() {
    if (app.extensions?.some((extension) => extension.name === NB_EXTENSION)) return;
    install();
  },
});
