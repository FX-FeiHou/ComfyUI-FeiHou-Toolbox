import { app } from "../../scripts/app.js";

const NODE_NAME = "ImageBatchMultiV2";

function setupDynamicImageInputs(node) {
  const rebuild = () => {
    if (!node.inputs) node.inputs = [];
    const countWidget = node.widgets?.find((widget) => widget.name === "inputcount");
    if (!countWidget) return;
    const target = Math.max(2, Math.floor(Number(countWidget.value) || 2));
    const imageInputs = node.inputs.filter((input) => input.name?.startsWith("image_"));
    const current = imageInputs.length;

    if (target === current) return;
    if (target < current) {
      for (let index = node.inputs.length - 1; index >= 0; index--) {
        const input = node.inputs[index];
        const match = String(input?.name || "").match(/^image_(\d+)$/);
        if (match && Number(match[1]) > target) {
          node.removeInput(index);
        }
      }
    } else {
      for (let index = current + 1; index <= target; index++) {
        node.addInput(`image_${index}`, "IMAGE", { shape: 7 });
      }
    }
    app.graph?.setDirtyCanvas?.(true, true);
  };

  node.addWidget("button", "Update inputs", null, rebuild);
  const countWidget = node.widgets?.find((widget) => widget.name === "inputcount");
  if (countWidget) {
    const originalCallback = countWidget.callback;
    countWidget.callback = function (value, canvas) {
      const result = originalCallback?.apply(this, arguments);
      if (!canvas) rebuild();
      return result;
    };
  }
  requestAnimationFrame(rebuild);
}

app.registerExtension({
  name: "FeiHou.ImageBatchMultiV2",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      setupDynamicImageInputs(this);
      return result;
    };
  },
});
