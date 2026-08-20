import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "RandomSeedNoise";
const RANDOM_MAX = 1125899906842624;
const SPECIAL_SEEDS = new Set([-1, -2, -3]);

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

function labels() {
  if (isChineseLocale()) {
    return {
      randomEach: "🎲 每次排队随机",
      fixedRandom: "🎲 新建固定随机种子",
      lastSeed: "♻️ 使用上次排队种子",
      title: "随机种子噪波",
    };
  }
  return {
    randomEach: "🎲 Randomize Each Queue",
    fixedRandom: "🎲 New Fixed Random Seed",
    lastSeed: "♻️ Use Last Queued Seed",
    title: "Random Seed Noise",
  };
}

function randomSeed() {
  // RANDOM_MAX is safely within JavaScript's integer precision limit.
  return Math.floor(Math.random() * RANDOM_MAX) + 1;
}

function seedWidget(node) {
  return node.widgets?.find((widget) => widget.name === "seed");
}

function isInactive(node) {
  return node.mode === 2 || node.mode === 4;
}

function getSeedToQueue(node) {
  const widget = seedWidget(node);
  const inputSeed = Number(widget?.value);
  if (!SPECIAL_SEEDS.has(inputSeed)) return inputSeed;

  if (typeof node._fhLastQueuedSeed === "number") {
    if (inputSeed === -2) {
      const next = node._fhLastQueuedSeed + 1;
      if (!SPECIAL_SEEDS.has(next) && next <= RANDOM_MAX) return next;
    }
    if (inputSeed === -3) {
      const next = node._fhLastQueuedSeed - 1;
      if (!SPECIAL_SEEDS.has(next) && next >= -RANDOM_MAX) return next;
    }
  }
  return randomSeed();
}

function updateLastSeedButton(node, queuedSeed) {
  const widget = node._fhLastSeedButton;
  if (!widget) return;
  const currentSeed = Number(seedWidget(node)?.value);
  const translated = labels();
  const usingGeneratedSeed = queuedSeed !== currentSeed;
  widget.label = usingGeneratedSeed ? `♻️ ${queuedSeed}` : translated.lastSeed;
  widget.name = widget.label;
  widget.disabled = !usingGeneratedSeed;
}

function updateWorkflowSeed(prompt, node, queuedSeed) {
  const output = prompt?.output || prompt?.prompt || prompt;
  const promptNode = output?.[String(node.id)];
  if (promptNode?.class_type !== NODE_NAME || !promptNode.inputs) return;

  promptNode.inputs.seed = queuedSeed;
  const workflowNode = prompt?.workflow?.nodes?.find((item) => String(item?.id) === String(node.id));
  if (Array.isArray(workflowNode?.widgets_values)) {
    const index = node.widgets?.indexOf(seedWidget(node)) ?? -1;
    if (index >= 0) workflowNode.widgets_values[index] = queuedSeed;
  }
}

function patchQueuePrompt() {
  if (api.queuePrompt?._fhRandomSeedNoisePatched || typeof api.queuePrompt !== "function") return;
  const originalQueuePrompt = api.queuePrompt;
  api.queuePrompt = async function (...args) {
    // The prompt argument is conventionally the second argument. Finding it by shape also
    // covers frontend variants that add extra positional arguments.
    const prompt = args.find((value) => value && typeof value === "object" && (value.output || value.prompt));
    if (prompt && app.graph?._nodes) {
      for (const node of app.graph._nodes) {
        if (node.comfyClass !== NODE_NAME || isInactive(node)) continue;
        const queuedSeed = getSeedToQueue(node);
        updateWorkflowSeed(prompt, node, queuedSeed);
        node._fhLastQueuedSeed = queuedSeed;
        updateLastSeedButton(node, queuedSeed);
      }
    }
    return originalQueuePrompt.apply(this, args);
  };
  api.queuePrompt._fhRandomSeedNoisePatched = true;
}

function addControls(node) {
  if (node._fhRandomSeedNoiseReady) return;
  node._fhRandomSeedNoiseReady = true;

  // ComfyUI automatically adds this widget for integer inputs. rgthree's Seed
  // node removes it because its three seed buttons replace that behavior.
  for (let index = node.widgets.length - 1; index >= 0; index -= 1) {
    if (node.widgets[index].name === "control_after_generate") {
      node.widgets.splice(index, 1);
    }
  }
  const widget = seedWidget(node);
  if (!widget) return;

  // Match rgthree's fresh-node behavior: randomize for every queue by default.
  if (widget.value === 0 || widget.value === undefined || widget.value === null) widget.value = -1;
  const translated = labels();
  node.addWidget("button", translated.randomEach, null, () => {
    widget.value = -1;
    updateLastSeedButton(node, Number(widget.value));
  }, { serialize: false });
  node.addWidget("button", translated.fixedRandom, null, () => {
    widget.value = randomSeed();
    updateLastSeedButton(node, Number(widget.value));
  }, { serialize: false });
  node._fhLastSeedButton = node.addWidget("button", translated.lastSeed, null, () => {
    if (typeof node._fhLastQueuedSeed === "number") widget.value = node._fhLastQueuedSeed;
    updateLastSeedButton(node, Number(widget.value));
  }, { serialize: false });
  node._fhLastSeedButton.disabled = true;
}

app.registerExtension({
  name: "FeiHou.RandomSeedNoise",
  setup() {
    patchQueuePrompt();
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;
    const created = nodeType.prototype.onNodeCreated;
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onNodeCreated = function () {
      const result = created?.apply(this, arguments);
      addControls(this);
      return result;
    };
    nodeType.prototype.onConfigure = function () {
      const result = configured?.apply(this, arguments);
      addControls(this);
      return result;
    };
  },
});
