import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { setWidgetConfig } from "../../extensions/core/widgetInputs.js";
import { applyTextReplacements } from "../../scripts/utils.js";

// The V2 backend only changes final-file saving.  This frontend retains the
// VideoHelperSuite Video Combine state, preview, and context-menu behavior.
const NODE_NAME = "VideoCombineV2";

function chainCallback(object, property, callback) {
  if (object === undefined) {
    console.error("Tried to add callback to non-existent object");
    return;
  }
  if (property in object && object[property]) {
    const original = object[property];
    object[property] = function () {
      const result = original.apply(this, arguments);
      return callback.apply(this, arguments) ?? result;
    };
  } else object[property] = callback;
}

const convDict = {
  [NODE_NAME]: ["frame_rate", "loop_count", "filename_prefix", "format", "pingpong", "save_output"],
};

function useKVState(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    chainCallback(this, "onConfigure", function (info) {
      if (!this.widgets || typeof info.widgets_values !== "object") return;
      let widgetDict = info.widgets_values;
      if (info.widgets_values.length) {
        const convList = convDict[this.type];
        if (convList && info.widgets_values.length >= convList.length) {
          widgetDict = {};
          for (let index = 0; index < convList.length; index++) {
            if (convList[index]) widgetDict[convList[index]] = info.widgets_values[index];
          }
        }
      }
      if (widgetDict.videopreview?.params?.force_size) delete widgetDict.videopreview.params.force_size;
      const inputs = {};
      for (const input of this.inputs) inputs[input.name] = input;
      if (widgetDict.length === undefined) {
        for (const widget of this.widgets) {
          if (widget.type === "button") continue;
          if (widget.name in widgetDict) {
            widget.value = widgetDict[widget.name];
            widget.callback?.(widget.value);
          } else {
            const nodeInputs = LiteGraph.getNodeType(this.type).nodeData.input;
            let initialValue = null;
            if (nodeInputs?.required?.hasOwnProperty(widget.name)) {
              if (nodeInputs.required[widget.name][1]?.hasOwnProperty("default")) initialValue = nodeInputs.required[widget.name][1].default;
              else if (nodeInputs.required[widget.name][0].length) initialValue = nodeInputs.required[widget.name][0][0];
            } else if (nodeInputs?.optional?.hasOwnProperty(widget.name)) {
              if (nodeInputs.optional[widget.name][1]?.hasOwnProperty("default")) initialValue = nodeInputs.optional[widget.name][1].default;
              else if (nodeInputs.optional[widget.name][0].length) initialValue = nodeInputs.optional[widget.name][0][0];
            }
            if (initialValue) {
              widget.value = initialValue;
              widget.callback?.(widget.value);
            }
          }
          if (widget.name in inputs && widget.config) setWidgetConfig(inputs[widget.name], widget.config);
        }
      } else if (info.widgets_values.length !== this.widgets.length) {
        app.ui.dialog.show(`Failed to restore node: ${this.title}\nPlease remove and re-add it.`);
        this.bgcolor = "#C00";
      }
    });
    chainCallback(this, "onSerialize", function (info) {
      info.widgets_values = {};
      if (!this.widgets) return;
      for (const widget of this.widgets) info.widgets_values[widget.name] = widget.value;
    });
  });
}

function useVhsNodeBehavior(nodeType, nodeData) {
  // This is the node-specific portion of VHS.core.js' shared VHS setup.  It
  // keeps the original Video Combine numeric widgets and dynamic-widget input
  // configuration instead of substituting ComfyUI defaults.
  for (const input of Object.values({ ...nodeData.input?.required, ...nodeData.input?.optional })) {
    if (["INT", "FLOAT"].includes(input[0])) {
      input[1] ??= {};
      input[1].widgetType ??= `VHS${input[0]}`;
    }
  }
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const originalAddInput = this.addInput;
    this.addInput = function (name, type, options) {
      if (options?.widget) {
        const widget = this.widgets.find((item) => item.name === name);
        if (widget?.config) {
          type = widget.config[0];
          if (type === "FLOAT") type = "FLOAT,INT";
          setWidgetConfig(options, widget.config);
        }
      }
      return originalAddInput.apply(this, [name, type, options]);
    };
  });
}

function fitHeight(node) {
  node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
  node.graph?.setDirtyCanvas(true);
}

function startDraggingItems(node, pointer) {
  app.canvas.emitBeforeChange();
  app.canvas.graph?.beforeChange();
  pointer.finally = () => {
    app.canvas.isDragging = false;
    app.canvas.graph?.afterChange();
    app.canvas.emitAfterChange();
  };
  app.canvas.processSelect(node, pointer.eDown, true);
  app.canvas.isDragging = true;
}

function processDraggedItems(event) {
  if (event.shiftKey || LiteGraph.alwaysSnapToGrid) app.canvas?.graph?.snapToGrid(app.canvas.selectedItems);
  app.canvas.dirty_canvas = true;
  app.canvas.dirty_bgcanvas = true;
  app.canvas.onNodeMoved?.(Object.values(app.canvas.selectedItems ?? {})[0]);
}

function allowDragFromWidget(widget) {
  widget.onPointerDown = function (pointer, node) {
    pointer.onDragStart = () => startDraggingItems(node, pointer);
    pointer.onDragEnd = processDraggedItems;
    app.canvas.dirty_canvas = true;
    return true;
  };
}

function addVAEInputToggle(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    this.reject_ue_connection = (input) => input?.name === "vae";
  });
  chainCallback(nodeType.prototype, "onConnectionsChange", function (contype, slot, iscon, linkInfo) {
    if (contype !== LiteGraph.INPUT || slot !== 3 || this.inputs[3].type !== "VAE") return;
    if (iscon && linkInfo) {
      if (this.linkTimeout) {
        clearTimeout(this.linkTimeout);
        this.linkTimeout = false;
      } else if (this.inputs[0].type === "IMAGE") {
        this.linkTimeout = setTimeout(() => {
          if (this.inputs[0].type !== "IMAGE") return;
          this.linkTimeout = false;
          this.disconnectInput(0);
        }, 50);
      }
      this.inputs[0].type = "LATENT";
    } else {
      if (this.inputs[0].type === "LATENT") {
        this.linkTimeout = setTimeout(() => {
          this.linkTimeout = false;
          this.disconnectInput(0);
        }, 50);
      }
      this.inputs[0].type = "IMAGE";
    }
  });
}

function addDateFormatting(nodeType, field) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const widget = this.widgets.find((item) => item.name === field);
    widget.serializeValue = () => applyTextReplacements(app, widget.value);
  });
}

function addVideoPreview(nodeType, isInput = true) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const element = document.createElement("div");
    const previewNode = this;
    const previewWidget = this.addDOMWidget("videopreview", "preview", element, {
      serialize: false,
      hideOnZoom: false,
      getValue() { return element.value; },
      setValue(value) { element.value = value; },
    });
    allowDragFromWidget(previewWidget);
    previewWidget.computeSize = function (width) {
      if (this.aspectRatio && !this.parentEl.hidden) {
        let height = (previewNode.size[0] - 20) / this.aspectRatio + 10;
        if (!(height > 0)) height = 0;
        this.computedHeight = height + 10;
        return [width, height];
      }
      return [width, -4];
    };
    element.addEventListener("contextmenu", (event) => { event.preventDefault(); return app.canvas._mousedown_callback(event); }, true);
    element.addEventListener("pointerdown", (event) => { event.preventDefault(); return app.canvas._mousedown_callback(event); }, true);
    element.addEventListener("mousewheel", (event) => { event.preventDefault(); return app.canvas._mousewheel_callback(event); }, true);
    element.addEventListener("pointermove", (event) => { event.preventDefault(); return app.canvas._mousemove_callback(event); }, true);
    element.addEventListener("pointerup", (event) => { event.preventDefault(); return app.canvas._mouseup_callback(event); }, true);
    element.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      app.dragOverNode = this;
    });

    previewWidget.value = { hidden: false, paused: false, params: {}, muted: app.ui.settings.getSettingValue("VHS.DefaultMute") };
    previewWidget.parentEl = document.createElement("div");
    previewWidget.parentEl.className = "vhs_preview";
    previewWidget.parentEl.style.width = "100%";
    element.appendChild(previewWidget.parentEl);
    previewWidget.videoEl = document.createElement("video");
    previewWidget.videoEl.controls = false;
    previewWidget.videoEl.loop = true;
    previewWidget.videoEl.muted = true;
    previewWidget.videoEl.style.width = "100%";
    previewWidget.videoEl.addEventListener("loadedmetadata", () => {
      previewWidget.aspectRatio = previewWidget.videoEl.videoWidth / previewWidget.videoEl.videoHeight;
      fitHeight(this);
    });
    previewWidget.videoEl.addEventListener("error", () => {
      previewWidget.parentEl.hidden = true;
      fitHeight(this);
    });
    previewWidget.videoEl.onmouseenter = () => { previewWidget.videoEl.muted = previewWidget.value.muted; };
    previewWidget.videoEl.onmouseleave = () => { previewWidget.videoEl.muted = true; };
    previewWidget.imgEl = document.createElement("img");
    previewWidget.imgEl.style.width = "100%";
    previewWidget.imgEl.hidden = true;
    previewWidget.imgEl.onload = () => {
      previewWidget.aspectRatio = previewWidget.imgEl.naturalWidth / previewWidget.imgEl.naturalHeight;
      fitHeight(this);
    };
    previewWidget.parentEl.appendChild(previewWidget.videoEl);
    previewWidget.parentEl.appendChild(previewWidget.imgEl);

    let timeout = null;
    this.updateParameters = (params, forceUpdate) => {
      if (!previewWidget.value.params) {
        if (typeof previewWidget.value !== "object") previewWidget.value = { hidden: false, paused: false };
        previewWidget.value.params = {};
      }
      if (!Object.entries(params).some(([key, value]) => previewWidget.value.params[key] !== value)) return;
      Object.assign(previewWidget.value.params, params);
      if (!forceUpdate && app.ui.settings.getSettingValue("VHS.AdvancedPreviews") === "Never") return;
      if (timeout) clearTimeout(timeout);
      if (forceUpdate) previewWidget.updateSource();
      else timeout = setTimeout(() => previewWidget.updateSource(), 100);
    };
    previewWidget.updateSource = function () {
      if (this.value.params === undefined) return;
      const params = { ...this.value.params, timestamp: Date.now() };
      let advancedPreviews = app.ui.settings.getSettingValue("VHS.AdvancedPreviews");
      if (advancedPreviews === "Never") advancedPreviews = false;
      else if (advancedPreviews === "Input Only") advancedPreviews = isInput;
      else advancedPreviews = true;
      this.parentEl.hidden = this.value.hidden;
      if (params.format?.split("/")[0] === "video" || advancedPreviews && params.format?.split("/")[1] === "gif" || params.format === "folder") {
        this.videoEl.autoplay = !this.value.paused && !this.value.hidden;
        if (!advancedPreviews) this.videoEl.src = api.apiURL(`/view?${new URLSearchParams(params)}`);
        else {
          let targetWidth = (previewNode.size[0] - 20) * 2 || 256;
          const minWidth = app.ui.settings.getSettingValue("VHS.AdvancedPreviewsMinWidth");
          if (targetWidth < minWidth) targetWidth = minWidth;
          if (!params.custom_width || !params.custom_height) params.force_size = `${targetWidth}x?`;
          else params.force_size = `${targetWidth}x${targetWidth / (params.custom_width / params.custom_height)}`;
          params.deadline = app.ui.settings.getSettingValue("VHS.AdvancedPreviewsDeadline");
          this.videoEl.src = api.apiURL(`/feihou-vhs/viewvideo?${new URLSearchParams(params)}`);
        }
        this.videoEl.hidden = false;
        this.imgEl.hidden = true;
      } else if (params.format?.split("/")[0] === "image") {
        this.imgEl.src = api.apiURL(`/view?${new URLSearchParams(params)}`);
        this.videoEl.hidden = true;
        this.imgEl.hidden = false;
      }
      delete previewNode.video_query;
      const doQuery = async () => {
        if (!previewWidget?.value?.params?.filename) return;
        try {
          const response = await fetch(api.apiURL(`/feihou-vhs/queryvideo?${new URLSearchParams(previewWidget.value.params)}`));
          previewNode.video_query = await response.json();
        } catch (_) { /* optional VHS video-information endpoint */ }
      };
      doQuery();
    };
    previewWidget.callback = previewWidget.updateSource;
  });
}

let copiedPath = undefined;
function addPreviewOptions(nodeType) {
  chainCallback(nodeType.prototype, "getExtraMenuOptions", function (_, options) {
    const previewWidget = this.widgets.find((widget) => widget.name === "videopreview");
    const newOptions = [];
    let url = null;
    if (previewWidget.videoEl?.hidden === false && previewWidget.videoEl.src) {
      if (["input", "output", "temp"].includes(previewWidget.value.params.type)) {
        url = api.apiURL(`/view?${new URLSearchParams(previewWidget.value.params)}`).replace("%2503d", "001");
      }
    } else if (previewWidget.imgEl?.hidden === false && previewWidget.imgEl.src) url = new URL(previewWidget.imgEl.src);
    if (this.video_query?.source) {
      const source = this.video_query.source;
      newOptions.push({ content: `${source.size.join("x")}@${source.fps}fps ${source.frames}frames`, disabled: true });
    }
    if (url) {
      newOptions.push({ content: "Open preview", callback: () => window.open(url, "_blank") });
      newOptions.push({ content: "Save preview", callback: () => {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.setAttribute("download", previewWidget.value.params.filename);
        document.body.append(anchor);
        anchor.click();
        requestAnimationFrame(() => anchor.remove());
      }});
      if (previewWidget.value.params.fullpath) {
        copiedPath = previewWidget.value.params.fullpath;
        newOptions.push({ content: "Copy output filepath", callback: async () => navigator.clipboard.writeText(previewWidget.value.params.fullpath) });
      }
      if (previewWidget.value.params.workflow) {
        const workflowParams = { ...previewWidget.value.params, filename: previewWidget.value.params.workflow };
        newOptions.push({ content: "Save workflow image", callback: () => {
          const anchor = document.createElement("a");
          anchor.href = api.apiURL(`/view?${new URLSearchParams(workflowParams)}`);
          anchor.setAttribute("download", previewWidget.value.params.workflow);
          document.body.append(anchor);
          anchor.click();
          requestAnimationFrame(() => anchor.remove());
        }});
      }
    }
    if (previewWidget.videoEl.hidden === false) {
      newOptions.push({ content: `${previewWidget.value.paused ? "Resume" : "Pause"} preview`, callback: () => {
        if (previewWidget.value.paused) previewWidget.videoEl.play(); else previewWidget.videoEl.pause();
        previewWidget.value.paused = !previewWidget.value.paused;
      }});
    }
    newOptions.push({ content: `${previewWidget.value.hidden ? "Show" : "Hide"} preview`, callback: () => {
      if (!previewWidget.videoEl.hidden && !previewWidget.value.hidden) previewWidget.videoEl.pause();
      else if (previewWidget.value.hidden && !previewWidget.videoEl.hidden && !previewWidget.value.paused) previewWidget.videoEl.play();
      previewWidget.value.hidden = !previewWidget.value.hidden;
      previewWidget.parentEl.hidden = previewWidget.value.hidden;
      fitHeight(this);
    }});
    newOptions.push({ content: "Sync preview", callback: () => {
      for (const preview of document.getElementsByClassName("vhs_preview")) {
        for (const child of preview.children) {
          if (child.tagName === "VIDEO") child.currentTime = 0;
          else if (child.tagName === "IMG") child.src = child.src;
        }
      }
    }});
    newOptions.push({ content: `${previewWidget.value.muted ? "Unmute" : "Mute"} Preview`, callback: () => { previewWidget.value.muted = !previewWidget.value.muted; } });
    if (options.length > 0 && options[0] !== null && newOptions.length > 0) newOptions.push(null);
    options.unshift(...newOptions);
  });
}

function addFormatWidgets(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    let formatWidget = null;
    let formatWidgetIndex = -1;
    for (let index = 0; index < this.widgets.length; index++) {
      if (this.widgets[index].name === "format") {
        formatWidget = this.widgets[index];
        formatWidgetIndex = index + 1;
        break;
      }
    }
    let formatWidgetsCount = 0;
    chainCallback(formatWidget, "callback", (value) => {
      const formats = LiteGraph.registered_node_types[this.type]?.nodeData?.input?.required?.format?.[1]?.formats;
      const newWidgets = [];
      if (formats?.[value]) {
        for (const definition of formats[value]) {
          let type = definition[2]?.widgetType ?? definition[1];
          if (Array.isArray(type)) type = "COMBO";
          app.widgets[type](this, definition[0], definition.slice(1), app);
          const widget = this.widgets.pop();
          widget.config = definition.slice(1);
          newWidgets.push(widget);
        }
      }
      const removed = this.widgets.splice(formatWidgetIndex, formatWidgetsCount, ...newWidgets);
      const newNames = new Set(newWidgets.map((widget) => widget.name));
      for (const widget of removed) {
        widget?.onRemove?.();
        if (newNames.has(widget.name)) continue;
        const slot = this.inputs.findIndex((input) => input.name === widget.name);
        if (slot >= 0) this.removeInput(slot);
      }
      for (const widget of newWidgets) {
        const existingInput = this.inputs.find((input) => input.name === widget.name);
        if (existingInput) setWidgetConfig(existingInput, widget.config);
        else this.addInput(widget.name, widget.config[0], { widget: { name: widget.name } });
      }
      fitHeight(this);
      formatWidgetsCount = newWidgets.length;
    });
  });
}

app.registerExtension({
  name: "FeiHou.VideoCombineV2",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_NAME) return;
    useKVState(nodeType);
    useVhsNodeBehavior(nodeType, nodeData);
    addDateFormatting(nodeType, "filename_prefix");
    chainCallback(nodeType.prototype, "onExecuted", function (message) {
      if (message?.gifs) this.updateParameters(message.gifs[0], true);
    });
    addVideoPreview(nodeType, false);
    addPreviewOptions(nodeType);
    addFormatWidgets(nodeType);
    addVAEInputToggle(nodeType);
  },
});
