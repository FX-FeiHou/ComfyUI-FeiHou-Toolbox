import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { installMediaLoader, installPromptMentions, migrateLegacyGallery } from "./feihou_api_media.js";

const NODE_NAMES = new Set(["FeiHouApiImage", "FeiHouApiVideo"]);

function isChineseLocale() {
  const locale = app.ui?.settings?.getSettingValue?.("Comfy.Locale") || navigator.language || "en";
  return /^zh(?:[-_]|$)/i.test(String(locale));
}

function t(zh, en) {
  return isChineseLocale() ? zh : en;
}

function chainCallback(object, property, callback) {
  const original = object?.[property];
  object[property] = function () {
    const result = original?.apply(this, arguments);
    return callback.apply(this, arguments) ?? result;
  };
}

function widget(node, name) {
  return node.widgets?.find((entry) => entry.name === name);
}

function applyModels(node, models, preferred = "") {
  const modelWidget = widget(node, "model");
  if (!modelWidget) return;
  const choices = [...new Set((models || []).map((item) => String(item || "").trim()).filter(Boolean))];
  if (preferred && !choices.includes(preferred)) choices.unshift(preferred);
  modelWidget.options.values = choices.length ? choices : [""];
  if (!choices.includes(modelWidget.value)) modelWidget.value = choices.includes(preferred) ? preferred : choices[0] || "";
  node.properties ||= {};
  node.properties.fh_api_models = choices;
  node.graph?.setDirtyCanvas(true);
}

function localize(node, nodeName) {
  // Old workflows can retain an image socket even after the backend schema changed.
  for (let i=(node.inputs?.length||0)-1;i>=0;i--) {
    if (!["image","reference_image"].includes(node.inputs[i].name)) continue;
    const current=node.inputs.findIndex(input=>input.name==="media");
    if (current<0) { node.inputs[i].name="media";continue; }
    const legacy=node.graph?.links?.[node.inputs[i].link];
    if (legacy && node.inputs[current].link==null) {
      node.graph?.getNodeById?.(legacy.origin_id)?.connect?.(legacy.origin_slot,node,current);
    }
    node.removeInput(i);
  }
  node.title = nodeName === "FeiHouApiImage" ? "FeiHou-API Images" : "FeiHou-API Video";
  const labels = {
    api_key: t("API Key", "API Key"),
    model: t("模型", "Model"),
    prompt: t("提示词", "Prompt"),
    resolution: t("分辨率", "Resolution"),
    aspect_ratio: t("画面比例", "Aspect ratio"),
    width: t("自定义宽度", "Custom width"),
    height: t("自定义高度", "Custom height"),
    output_format: t("图片格式", "Image format"),
    duration: t("时长（秒，-1 自动）", "Duration (seconds, -1 auto)"),
    seed: t("种子（-1 随机）", "Seed (-1 random)"),
    generate_audio: t("生成音频", "Generate audio"),
    return_last_frame: t("请求返回尾帧", "Request last frame"),
  };
  for (const [name, label] of Object.entries(labels)) {
    const current = widget(node, name);
    if (current) current.label = label;
  }
  const apiKey = widget(node, "api_key");
  if (apiKey) apiKey.tooltip = t("仅发送至 api.fei-hou.net；含有 API Key 的工作流不要分享给他人。", "Sent only to api.fei-hou.net. Do not share a workflow containing this API key.");
  const media = node.inputs?.find((input) => input.name === "media" || input.name === "image");
  if (media) {
    media.name = "media";
    media.type = "*";
    media.label = media.localized_name = t("媒体输入", "Media input");
  }
}

async function updateParameters(node, nodeName) {
  const model = String(widget(node, "model")?.value || "");
  const kind = nodeName === "FeiHouApiImage" ? "image" : "video";
  const revision = node._fhParameterRevision = (node._fhParameterRevision || 0) + 1;
  try {
    const response = await api.fetchApi(`/feihou/api/parameters?${new URLSearchParams({ model, kind })}`);
    if (!response.ok) throw new Error(`Parameter options: HTTP ${response.status}`);
    const options = await response.json();
    if (revision !== node._fhParameterRevision) return;
    localize(node, nodeName);
    for (const name of ["resolution", "aspect_ratio", "duration"]) {
      const current = widget(node, name);
      if (!current) continue;
      current.options.values = options[name];
      if (!options[name].includes(String(current.value))) current.value = "default";
      current.disabled = options[name].length <= 1;
      current.tooltip = t("default：采用模型默认值；选项随模型变化。", "default: use the model default; choices depend on the model.");
    }
    const enabled = {
      width: options.custom_size && widget(node, "resolution")?.value === "custom",
      height: options.custom_size && widget(node, "resolution")?.value === "custom",
      output_format: options.output_format,
      seed: options.seed,
      generate_audio: options.generate_audio,
      return_last_frame: options.return_last_frame,
    };
    for (const [name, active] of Object.entries(enabled)) {
      const current = widget(node, name);
      if (!current) continue;
      current.disabled = !active;
      current.tooltip = active ? "" : t("当前模型或尺寸模式不使用此参数。", "Not used by the current model or sizing mode.");
      if (!active) current.label += t("（不适用）", " (not applicable)");
    }
    node.graph?.setDirtyCanvas(true);
  } catch (error) {
    console.warn("FeiHou parameter options could not be loaded", error);
  }
}

function addRefreshButton(node) {
  const refresh = node.addWidget("button", "refresh_models", t("刷新模型列表", "Refresh models"), async () => {
    const key = String(widget(node, "api_key")?.value || "").trim();
    if (!key) {
      alert(t("请先填写 API Key。", "Enter an API key first."));
      return;
    }
    const originalLabel = refresh.label;
    refresh.label = t("正在刷新…", "Refreshing…");
    node.graph?.setDirtyCanvas(true);
    try {
      const response = await api.fetchApi("/feihou/api/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: key,
          kind: (node.comfyClass || node.type) === "FeiHouApiImage" ? "image" : "video",
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.error || t("模型列表刷新失败。", "Could not refresh models."));
      applyModels(node, payload.models, String(widget(node, "model")?.value || ""));
      await updateParameters(node, node.comfyClass || node.type);
    } catch (error) {
      alert(error?.message || t("模型列表刷新失败。", "Could not refresh models."));
    } finally {
      refresh.label = originalLabel;
      node.graph?.setDirtyCanvas(true);
    }
  });
  refresh.options.serialize = false;
  refresh.label = refresh.name = t("刷新模型列表", "Refresh models");
  const modelWidget = widget(node, "model");
  const modelIndex = node.widgets.indexOf(modelWidget);
  const refreshIndex = node.widgets.indexOf(refresh);
  if (modelIndex >= 0 && refreshIndex >= 0) {
    node.widgets.splice(refreshIndex, 1);
    node.widgets.splice(modelIndex + 1, 0, refresh);
  }
}

app.registerExtension({
  name: "FeiHou.ApiNodes",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name === "FeiHouApiMediaLoader") {
      chainCallback(nodeType.prototype, "onNodeCreated", function () {
        this.title = "FeiHou-API Media";
        installMediaLoader(this,t);
      });
      chainCallback(nodeType.prototype, "onConfigure", function () { this.title="FeiHou-API Media";this._fhMediaPanel?.restore(); });
      chainCallback(nodeType.prototype, "onRemoved", function () { this._fhMediaPanel?.dispose(); });
      return;
    }
    if (!NODE_NAMES.has(nodeData?.name)) return;
    chainCallback(nodeType.prototype, "onNodeCreated", function () {
      localize(this, nodeData.name);
      applyModels(this, this.properties?.fh_api_models || [], String(widget(this, "model")?.value || ""));
      addRefreshButton(this);
      installPromptMentions(this, t);
      for (const name of ["model", "resolution"]) {
        const current = widget(this, name);
        if (current) chainCallback(current, "callback", () => { void updateParameters(this, nodeData.name); });
      }
      void updateParameters(this, nodeData.name);
    });
    chainCallback(nodeType.prototype, "onConfigure", function () {
      if (nodeData.name === "FeiHouApiVideo" && !this.outputs?.some(output => output.name === "last_frame")) {
        this.addOutput("last_frame", "IMAGE", { localized_name: t("尾帧", "Last frame") });
      }
      localize(this, nodeData.name);
      applyModels(this, this.properties?.fh_api_models || [], String(widget(this, "model")?.value || ""));
      this._fhPromptPanel?.restore();
      setTimeout(() => migrateLegacyGallery(this), 0);
      void updateParameters(this, nodeData.name);
    });
    chainCallback(nodeType.prototype, "onRemoved", function () {
      this._fhPromptPanel?.dispose();
    });
  },
});
