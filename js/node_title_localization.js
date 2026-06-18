import { app } from "../../scripts/app.js";

const TITLE_MAP = {
  SCAIL2ColoredMaskV2: {
    en: "Create SCAIL-2 Colored Mask V2",
    zh: "创建 SCAIL-2 彩色遮罩 V2",
  },
  AutoRefCollage: {
    en: "Auto Ref Collage",
    zh: "多参图像自动拼接",
  },
  ManualRefCollage: {
    en: "Manual Ref Collage",
    zh: "多参图像手动拼接",
  },
  ComfySwitchNodeV2: {
    en: "Switch V2",
    zh: "切换 V2",
  },
  InvertBoolean: {
    en: "Invert Boolean",
    zh: "反转布尔值",
  },
  ImageBatchMultiV2: {
    en: "Image Batch Multi V2",
    zh: "图像组合批次（多重）V2",
  },
  FastGroupsBypassSwitch: {
    en: "Fast Groups Bypass Switch",
    zh: "多框忽略并切换",
  },
};

function isChineseLocale() {
  const candidates = [
    app.ui?.settings?.getSettingValue?.("Comfy.Locale"),
    app.ui?.settings?.getSettingValue?.("Comfy.Language"),
    app.ui?.settings?.getSettingValue?.("Comfy.I18n.Locale"),
    navigator.language,
    ...(navigator.languages || []),
  ];
  return candidates.some((value) => String(value || "").toLowerCase().startsWith("zh"));
}

function getTitle(nodeName) {
  const entry = TITLE_MAP[nodeName];
  if (!entry) return null;
  return isChineseLocale() ? entry.zh : entry.en;
}

function applyTitle(node, nodeName) {
  const entry = TITLE_MAP[nodeName];
  const title = getTitle(nodeName);
  if (!entry || !title) return;
  if (!node.title || node.title === entry.en || node.title === entry.zh || node.title === nodeName) {
    node.title = title;
  }
}

app.registerExtension({
  name: "FeiHou.NodeTitleLocalization",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const title = getTitle(nodeData.name);
    const entry = TITLE_MAP[nodeData.name];
    if (!entry || !title) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    const onConfigure = nodeType.prototype.onConfigure;

    nodeData.display_name = title;
    nodeType.title = title;
    nodeType.prototype.title = title;

    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      applyTitle(this, nodeData.name);
      return result;
    };

    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      applyTitle(this, nodeData.name);
      return result;
    };
  },
});
