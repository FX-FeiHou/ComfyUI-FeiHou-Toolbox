import { app } from "../../scripts/app.js";

const NODE_NAME = "InvertBooleanFeiHou";
const TITLE_EN = "Invert Boolean";
const TITLE_ZH = "反转布尔值";

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

function localizedTitle() {
  return isChineseLocale() ? TITLE_ZH : TITLE_EN;
}

function applyTitle(node) {
  const title = localizedTitle();
  if (!node.title || node.title === TITLE_EN || node.title === TITLE_ZH || node.title === NODE_NAME) {
    node.title = title;
  }
}

app.registerExtension({
  name: "FeiHou.InvertBoolean",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const title = localizedTitle();
    nodeData.display_name = title;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    const onConfigure = nodeType.prototype.onConfigure;

    nodeType.title = title;
    nodeType.prototype.title = title;

    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      applyTitle(this);
      return result;
    };

    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      applyTitle(this);
      return result;
    };
  },
});
