import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "FeiHouVideoPreview";

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

function fitHeight(node) {
  node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
  node.graph?.setDirtyCanvas(true);
}

function passCanvasEvent(element, eventName, callbackName) {
  element.addEventListener(eventName, (event) => {
    event.preventDefault();
    return app.canvas[callbackName]?.(event);
  }, true);
}

function clearLocalBlob(previewWidget) {
  // Local object URLs can be shared by copy/pasted preview nodes.  They are
  // deliberately kept alive until the browser page closes instead of being
  // revoked when one of those nodes receives a newer source.
  previewWidget.localBlobUrl = null;
}

function addVideoPreview(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const node = this;
    const element = document.createElement("div");
    const previewWidget = this.addDOMWidget("videopreview", "preview", element, {
      serialize: false,
      hideOnZoom: false,
      getValue() { return element.value; },
      setValue(value) { element.value = value; },
    });
    previewWidget.computeSize = function (width) {
      if (this.aspectRatio && !this.parentEl.hidden) {
        const height = Math.max(0, (node.size[0] - 20) / this.aspectRatio + 10);
        return [width, height];
      }
      return [width, -4];
    };
    element.addEventListener("contextmenu", (event) => { event.preventDefault(); return app.canvas._mousedown_callback(event); }, true);
    passCanvasEvent(element, "pointerdown", "_mousedown_callback");
    passCanvasEvent(element, "mousewheel", "_mousewheel_callback");
    passCanvasEvent(element, "pointermove", "_mousemove_callback");
    passCanvasEvent(element, "pointerup", "_mouseup_callback");

    previewWidget.value = { hidden: false, paused: false, muted: false, params: {} };
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
      fitHeight(node);
    });
    previewWidget.videoEl.addEventListener("error", () => {
      previewWidget.parentEl.hidden = true;
      fitHeight(node);
    });
    // The default is silent. Hovering plays the audio unless the context-menu
    // mute state is enabled, exactly like Video Combine V2.
    previewWidget.videoEl.onmouseenter = () => { previewWidget.videoEl.muted = previewWidget.value.muted; };
    previewWidget.videoEl.onmouseleave = () => { previewWidget.videoEl.muted = true; };
    previewWidget.parentEl.appendChild(previewWidget.videoEl);

    previewWidget.showLocalFile = function (file) {
      clearLocalBlob(this);
      this.localBlobUrl = URL.createObjectURL(file);
      this.value.params = {
        filename: file.name || "preview.mp4",
        format: "video/h264-mp4",
        type: "local",
        // Keeping the object URL in the node state lets a copied node share
        // the same local preview during this browser session.
        local_url: this.localBlobUrl,
      };
      this.value.hidden = false;
      this.value.paused = false;
      this.parentEl.hidden = false;
      this.videoEl.src = this.localBlobUrl;
      this.videoEl.hidden = false;
      this.videoEl.muted = true;
      this.videoEl.autoplay = true;
      this.videoEl.play().catch(() => {});
      node.__feihouPreviewSource = "local";
      fitHeight(node);
    };

    let timeout = null;
    node.updateFeiHouPreview = (params, forceUpdate) => {
      // A workflow execution is a newer operation than a previously loaded
      // local video, so it always takes ownership of the visible preview.
      clearLocalBlob(previewWidget);
      node.__feihouPreviewSource = "workflow";
      previewWidget.value.params = { ...params };
      if (timeout) clearTimeout(timeout);
      if (forceUpdate) previewWidget.updateSource();
      else timeout = setTimeout(() => previewWidget.updateSource(), 100);
    };
    previewWidget.updateSource = function () {
      const params = this.value.params;
      if (!params?.filename || params.type === "local") return;
      const requestParams = { ...params, timestamp: Date.now() };
      this.parentEl.hidden = this.value.hidden;
      this.videoEl.autoplay = !this.value.paused && !this.value.hidden;
      this.videoEl.src = api.apiURL(`/view?${new URLSearchParams(requestParams)}`);
      this.videoEl.hidden = false;
    };
    previewWidget.callback = previewWidget.updateSource;
    // Do not revoke an object URL here: a copied node may still be using the
    // same local preview URL.  The browser releases it when the page closes.
  });
}

function addPreviewState(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    chainCallback(this, "onSerialize", function (info) {
      const previewWidget = this.widgets?.find((widget) => widget.name === "videopreview");
      const frameRate = this.widgets?.find((widget) => widget.name === "frame_rate");
      if (!previewWidget) return;
      const params = { ...(previewWidget.value?.params || {}) };
      if (params.type === "local" && previewWidget.localBlobUrl) params.local_url = previewWidget.localBlobUrl;
      // DOM widgets are intentionally non-serializable.  Store only their
      // lightweight playback state, so copy/paste behaves like Video Combine
      // V2 while never serializing media bytes.
      info.widgets_values = {
        frame_rate: frameRate?.value,
        videopreview: {
          hidden: Boolean(previewWidget.value?.hidden),
          paused: Boolean(previewWidget.value?.paused),
          muted: Boolean(previewWidget.value?.muted),
          params,
        },
      };
    });
    chainCallback(this, "onConfigure", function (info) {
      const saved = info?.widgets_values;
      if (!saved || Array.isArray(saved)) return;
      const frameRate = this.widgets?.find((widget) => widget.name === "frame_rate");
      if (frameRate && saved.frame_rate != null) {
        frameRate.value = saved.frame_rate;
        frameRate.callback?.(frameRate.value);
      }
      const previewWidget = this.widgets?.find((widget) => widget.name === "videopreview");
      const state = saved.videopreview;
      if (!previewWidget || !state?.params?.filename) return;
      previewWidget.value = {
        hidden: Boolean(state.hidden),
        paused: Boolean(state.paused),
        muted: Boolean(state.muted),
        params: { ...state.params },
      };
      previewWidget.parentEl.hidden = previewWidget.value.hidden;
      if (state.params.type === "local" && state.params.local_url) {
        previewWidget.localBlobUrl = state.params.local_url;
        previewWidget.videoEl.src = state.params.local_url;
        previewWidget.videoEl.hidden = false;
        previewWidget.videoEl.autoplay = !previewWidget.value.paused && !previewWidget.value.hidden;
        if (!previewWidget.value.paused && !previewWidget.value.hidden) previewWidget.videoEl.play().catch(() => {});
      } else {
        this.updateFeiHouPreview?.(state.params, true);
      }
    });
  });
}

function addLoadVideoButton(nodeType) {
  chainCallback(nodeType.prototype, "onNodeCreated", function () {
    const node = this;
    const fileInput = document.createElement("input");
    Object.assign(fileInput, {
      type: "file",
      accept: "video/*,video/webm,video/mp4,video/x-matroska,image/gif",
      style: "display: none",
    });
    fileInput.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      const previewWidget = node.widgets?.find((widget) => widget.name === "videopreview");
      if (file && previewWidget?.showLocalFile) previewWidget.showLocalFile(file);
      fileInput.value = "";
    });
    document.body.appendChild(fileInput);
    chainCallback(this, "onRemoved", () => fileInput.remove());

    const button = this.addWidget("button", "load_video", t("载入视频", "Load video"), () => {
      app.canvas.node_widget = null;
      fileInput.click();
    });
    button.options.serialize = false;
  });
}

function addPreviewOptions(nodeType) {
  chainCallback(nodeType.prototype, "getExtraMenuOptions", function (_, options) {
    const previewWidget = this.widgets?.find((widget) => widget.name === "videopreview");
    if (!previewWidget?.videoEl) return;
    const newOptions = [];
    const params = previewWidget.value?.params || {};
    let url = previewWidget.videoEl.src || null;
    if (params.type !== "local" && params.filename && ["input", "output", "temp"].includes(params.type)) {
      url = api.apiURL(`/view?${new URLSearchParams(params)}`).replace("%2503d", "001");
    }
    if (url) {
      newOptions.push({ content: t("打开预览", "Open preview"), callback: () => window.open(url, "_blank") });
      newOptions.push({ content: t("保存预览", "Save preview"), callback: () => {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.setAttribute("download", params.filename || "preview.mp4");
        document.body.append(anchor);
        anchor.click();
        requestAnimationFrame(() => anchor.remove());
      }});
    }
    if (previewWidget.videoEl.hidden === false) {
      newOptions.push({ content: previewWidget.value.paused ? t("继续预览", "Resume preview") : t("暂停预览", "Pause preview"), callback: () => {
        if (previewWidget.value.paused) previewWidget.videoEl.play();
        else previewWidget.videoEl.pause();
        previewWidget.value.paused = !previewWidget.value.paused;
      }});
    }
    newOptions.push({ content: previewWidget.value.hidden ? t("显示预览", "Show preview") : t("隐藏预览", "Hide preview"), callback: () => {
      if (!previewWidget.videoEl.hidden && !previewWidget.value.hidden) previewWidget.videoEl.pause();
      else if (previewWidget.value.hidden && !previewWidget.videoEl.hidden && !previewWidget.value.paused) previewWidget.videoEl.play();
      previewWidget.value.hidden = !previewWidget.value.hidden;
      previewWidget.parentEl.hidden = previewWidget.value.hidden;
      fitHeight(this);
    }});
    newOptions.push({ content: t("同步预览", "Sync preview"), callback: () => {
      for (const preview of document.getElementsByClassName("vhs_preview")) {
        for (const child of preview.children) if (child.tagName === "VIDEO") child.currentTime = 0;
      }
    }});
    newOptions.push({ content: previewWidget.value.muted ? t("取消静音预览", "Unmute preview") : t("静音预览", "Mute preview"), callback: () => {
      previewWidget.value.muted = !previewWidget.value.muted;
      previewWidget.videoEl.muted = true;
    }});
    if (options.length && newOptions.length) newOptions.push(null);
    options.unshift(...newOptions);
  });
}

function localizeNode(node) {
  node.title = t("FeiHou-视频预览", "FeiHou-Video Preview");
  const images = node.inputs?.find((input) => input.name === "images");
  if (images) images.label = images.localized_name = t("图像", "Images");
  const audio = node.inputs?.find((input) => input.name === "audio");
  if (audio) audio.label = audio.localized_name = t("音频", "Audio");
  const frameRate = node.widgets?.find((widget) => widget.name === "frame_rate");
  if (frameRate) frameRate.label = t("帧率", "Frame rate");
}

app.registerExtension({
  name: "FeiHou.VideoPreview",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE_NAME) return;
    chainCallback(nodeType.prototype, "onNodeCreated", function () { localizeNode(this); });
    chainCallback(nodeType.prototype, "onExecuted", function (message) {
      if (message?.gifs?.[0]) this.updateFeiHouPreview?.(message.gifs[0], true);
    });
    addLoadVideoButton(nodeType);
    addVideoPreview(nodeType);
    addPreviewState(nodeType);
    addPreviewOptions(nodeType);
  },
});
