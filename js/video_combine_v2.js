import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { applyTextReplacements } from "../../scripts/utils.js";

const NODE_NAME = "VideoCombineV2";

function chainCallback(object, property, callback) {
  const previous = object?.[property];
  object[property] = function () {
    const previousResult = previous?.apply(this, arguments);
    return callback.apply(this, arguments) ?? previousResult;
  };
}

function fitHeight(node) {
  node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
  node.graph?.setDirtyCanvas(true);
}

function addVhsPreview(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const node = this;
    const element = document.createElement("div");
    const preview = this.addDOMWidget("videopreview", "preview", element, {
      serialize: false,
      hideOnZoom: false,
    });
    preview.element = element;
    const video = document.createElement("video");
    const image = document.createElement("img");
    video.controls = false;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.style.width = "100%";
    image.style.width = "100%";
    image.hidden = true;
    element.style.width = "100%";
    element.append(video, image);

    preview.computeSize = (width) => {
      if (!preview.aspectRatio) return [width, -4];
      return [width, Math.max(0, (node.size[0] - 20) / preview.aspectRatio + 8)];
    };
    const updateSize = () => {
      const source = image.hidden ? video : image;
      const width = image.hidden ? source.videoWidth : source.naturalWidth;
      const height = image.hidden ? source.videoHeight : source.naturalHeight;
      if (width && height) {
        preview.aspectRatio = width / height;
        fitHeight(node);
      }
    };
    video.addEventListener("loadedmetadata", updateSize);
    image.addEventListener("load", updateSize);
    preview.value = { hidden: false, paused: false, muted: app.ui.settings.getSettingValue("VHS.DefaultMute") };
    video.addEventListener("canplay", () => {
      if (!preview.value.paused && !preview.value.hidden) video.play().catch(() => {});
    });
    // Exact VHS mute interaction: auto-play stays muted, entering the preview
    // applies the user's VHS preview-sound setting, leaving always mutes again.
    video.addEventListener("mouseenter", () => {
      video.muted = preview.value.muted;
      video.play().catch(() => {});
    });
    video.addEventListener("mouseleave", () => {
      video.muted = true;
    });
    video.addEventListener("error", () => {
      element.hidden = true;
      fitHeight(node);
    });

    node.updateVhsPreview = (params) => {
      if (!params?.filename) return;
      element.hidden = preview.value.hidden;
      const source = api.apiURL(`/view?${new URLSearchParams({
        filename: params.filename,
        subfolder: params.subfolder || "",
        type: params.type || "output",
        timestamp: Date.now(),
      })}`);
      if (String(params.format || "").startsWith("image/")) {
        video.pause();
        video.hidden = true;
        image.hidden = false;
        image.src = source;
      } else {
        image.hidden = true;
        video.hidden = false;
        video.autoplay = !preview.value.paused && !preview.value.hidden;
        video.muted = true;
        video.src = source;
        video.play().catch(() => {});
      }
    };

    chainCallback(node, "onExecuted", function (message) {
      node.updateVhsPreview(message?.gifs?.[0]);
    });
  });
}

function addVaeInputToggle(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    this.reject_ue_connection = (input) => input?.name === "vae";
  });
  chainCallback(nodeType.prototype, "onConnectionsChange", function (type, slot, connected, link) {
    if (type !== LiteGraph.INPUT || slot !== 3 || this.inputs[3]?.type !== "VAE") return;
    if (connected && link) {
      this.inputs[0].type = "LATENT";
    } else {
      this.inputs[0].type = "IMAGE";
    }
  });
}

function addPreviewOptions(nodeType) {
  chainCallback(nodeType.prototype, "getExtraMenuOptions", function (_, options) {
    const preview = this.widgets.find((widget) => widget.name === "videopreview");
    if (!preview) return;
    const extra = [];
    if (!preview.videoEl?.hidden) {
      extra.push({ content: `${preview.value.paused ? "Resume" : "Pause"} preview`, callback: () => {
        preview.value.paused ? preview.videoEl.play() : preview.videoEl.pause();
        preview.value.paused = !preview.value.paused;
      }});
    }
    extra.push({ content: `${preview.value.hidden ? "Show" : "Hide"} preview`, callback: () => {
      preview.value.hidden = !preview.value.hidden;
      preview.element.hidden = preview.value.hidden;
      if (preview.value.hidden) preview.videoEl?.pause();
      else if (!preview.value.paused) preview.videoEl?.play();
      fitHeight(this);
    }});
    extra.push({ content: `${preview.value.muted ? "Unmute" : "Mute"} Preview`, callback: () => {
      preview.value.muted = !preview.value.muted;
    }});
    if (extra.length) options.unshift(...extra, null);
  });
}

function addVhsFormatWidgets(nodeType, nodeData) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const formatWidgetIndex = this.widgets.findIndex((widget) => widget.name === "format");
    if (formatWidgetIndex < 0) return;

    const formatWidget = this.widgets[formatWidgetIndex];
    let dynamicCount = 0;
    const updateWidgets = (value) => {
      const formats = nodeData.input?.required?.format?.[1]?.formats;
      const definitions = formats?.[value] || [];
      const newWidgets = [];
      for (const definition of definitions) {
        let widgetType = definition[2]?.widgetType ?? definition[1];
        if (Array.isArray(widgetType)) widgetType = "COMBO";
        app.widgets[widgetType]?.(this, definition[0], definition.slice(1), app);
        const widget = this.widgets.pop();
        if (!widget) continue;
        widget.config = definition.slice(1);
        newWidgets.push(widget);
      }

      const removed = this.widgets.splice(formatWidgetIndex + 1, dynamicCount, ...newWidgets);
      const names = new Set(newWidgets.map((widget) => widget.name));
      for (const widget of removed) {
        widget?.onRemove?.();
        if (names.has(widget?.name)) continue;
        const slot = this.inputs.findIndex((input) => input.name === widget?.name);
        if (slot >= 0) this.removeInput(slot);
      }
      for (const widget of newWidgets) {
        if (!this.inputs.some((input) => input.name === widget.name)) {
          this.addInput(widget.name, widget.config?.[0], { widget: { name: widget.name } });
        }
      }
      dynamicCount = newWidgets.length;
      fitHeight(this);
    };

    chainCallback(formatWidget, "callback", updateWidgets);
    updateWidgets(formatWidget.value);

    const prefixWidget = this.widgets.find((widget) => widget.name === "filename_prefix");
    if (prefixWidget) prefixWidget.serializeValue = () => applyTextReplacements(app, prefixWidget.value);
  });
}

app.registerExtension({
  name: "FeiHou.VideoCombineV2",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;
    addVhsFormatWidgets(nodeType, nodeData);
    addVhsPreview(nodeType);
    addPreviewOptions(nodeType);
    addVaeInputToggle(nodeType);
  },
});
