const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const source = fs.readFileSync(path.join(__dirname, "../js/video_combine_v2.js"), "utf8");
    await page.route("**/*", async (route) => {
      if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
        return route.fulfill({ status: 403, body: "Read-only compatibility test" });
      }
      const pathname = new URL(route.request().url()).pathname;
      if (process.env.FEIHOU_NO_VHS === "1" && pathname.endsWith("/extensions")) {
        const response = await route.fetch();
        const extensions = await response.json();
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(
          extensions.filter((url) => !url.toLowerCase().includes("videohelpersuite"))) });
      }
      if (pathname.endsWith("/video_combine_v2.js")) {
        return route.fulfill({ contentType: "application/javascript", body: source });
      }
      return route.continue();
    });
    await page.goto("http://127.0.0.1:8188", { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => globalThis.LiteGraph?.registered_node_types?.VideoCombineV2, null, { timeout: 30000 });
    await page.waitForTimeout(1000);

    const result = await page.evaluate(async () => {
      const { app } = await import("/scripts/app.js");
      app.graph.clear();
      const inspect = (node) => {
        const names = node.widgets.map((widget) => widget.name);
        const widget = node.widgets.find((item) => item.name === "frame_rate");
        const slots = node.inputs.filter((item) => item.name === "frame_rate");
        return { names, value: widget?.value, type: widget?.type, slots: slots.length,
          slotType: slots[0]?.type, socketless: widget?.options?.socketless,
          link: slots[0]?.link ?? null };
      };
      const fresh = LiteGraph.createNode("VideoCombineV2");
      app.graph.add(fresh);
      const freshState = inspect(fresh);
      const named = LiteGraph.createNode("VideoCombineV2");
      app.graph.add(named);
      named.widgets = named.widgets.filter((widget) => widget.name !== "frame_rate");
      named.onConfigure({
        widgets_values: {
          frame_rate: 12,
          loop_count: 2,
          filename_prefix: "Named",
          format: "video/h264-mp4",
          pingpong: false,
          save_output: true,
        },
      });

      const legacy = LiteGraph.createNode("VideoCombineV2");
      app.graph.add(legacy);
      legacy.widgets = legacy.widgets.filter((widget) => widget.name !== "frame_rate");
      legacy.onConfigure({ widgets_values: [15, 3, "Legacy", "video/h264-mp4", false, true] });

      // Simulate v2.10.4: a saved node with its widget but no FPS slot.
      const socketless = LiteGraph.createNode("VideoCombineV2");
      app.graph.add(socketless);
      const socketlessInfo = socketless.serialize();
      socketlessInfo.inputs = socketlessInfo.inputs.filter((slot) => slot.name !== "frame_rate");
      socketlessInfo.widgets_values.frame_rate = 23.976;
      socketless.configure(socketlessInfo);
      const socketlessState = inspect(socketless);
      const expectedOldSlots = socketlessInfo.inputs.map((slot) => slot.name);
      if (JSON.stringify(socketless.inputs.slice(0, expectedOldSlots.length).map((slot) => slot.name)) !== JSON.stringify(expectedOldSlots)) throw new Error("Socket repair shifted old input indices");

      // Existing frame_rate links must keep their slot index and link ID.
      const floatSource = LiteGraph.createNode("PrimitiveFloat");
      const intSource = LiteGraph.createNode("PrimitiveInt");
      app.graph.add(floatSource);
      app.graph.add(intSource);
      const fpsIndex = fresh.inputs.findIndex((slot) => slot.name === "frame_rate");
      if (!floatSource.connect(0, fresh, fpsIndex)) throw new Error("FLOAT connection rejected");
      const floatLink = fresh.inputs[fpsIndex].link;
      const beforeOrder = fresh.inputs.map((slot) => slot.name);
      const connectedInfo = fresh.serialize();
      connectedInfo.widgets_values.frame_rate = 29.97;
      fresh.configure(connectedInfo);
      if (fresh.inputs[fpsIndex].link !== floatLink) throw new Error("FPS link changed on configure");
      if (JSON.stringify(fresh.inputs.map((slot) => slot.name)) !== JSON.stringify(beforeOrder)) throw new Error("Input order changed");
      // Simulate a legacy connected node without its numeric widget.
      fresh.widgets = fresh.widgets.filter((widget) => widget.name !== "frame_rate");
      fresh.onConfigure(connectedInfo);
      if (fresh.inputs[fpsIndex].link !== floatLink) throw new Error("FPS link lost on widget repair");
      const repairedConnected = inspect(fresh);
      const clone = fresh.clone();
      app.graph.add(clone);
      const cloned = inspect(clone);
      if (!intSource.connect(0, clone, clone.inputs.findIndex((slot) => slot.name === "frame_rate"))) throw new Error("INT connection rejected");

      const id = fresh.id;
      const graphInfo = app.graph.serialize();
      app.graph.configure(graphInfo);
      const restored = app.graph.getNodeById(id);
      const restoredState = inspect(restored);
      const savedLink = app.graph.links[restored.inputs[fpsIndex].link];
      if (!savedLink || savedLink.origin_id !== floatSource.id || savedLink.target_slot !== fpsIndex) throw new Error("Saved workflow FPS link changed");
      const prompt = (await app.graphToPrompt()).output;
      const linkedValue = prompt[String(id)].inputs.frame_rate;
      if (!Array.isArray(linkedValue) || String(linkedValue[0]) !== String(floatSource.id) || linkedValue[1] !== 0) throw new Error("FPS connection not forwarded to execution prompt");
      if (prompt[String(socketless.id)].inputs.frame_rate !== 23.976) throw new Error("Unlinked FPS widget not forwarded to execution prompt");
      return { fresh: freshState, named: inspect(named), legacy: inspect(legacy),
        socketless: socketlessState, repairedConnected, cloned, restored: restoredState };
    });

    for (const [label, state, expected] of [["named", result.named, 12], ["legacy", result.legacy, 15]]) {
      if (state.value !== expected || state.type !== "VHS.ANNOTATED") throw new Error(`${label} value/type: ${JSON.stringify(state)}`);
      if (state.names.indexOf("frame_rate") < 0 || state.names.indexOf("frame_rate") > state.names.indexOf("loop_count")) {
        throw new Error(`${label} order: ${JSON.stringify(state.names)}`);
      }
    }
    for (const [label, state] of Object.entries(result)) {
      if (state.slots !== 1 || state.socketless !== false) throw new Error(`${label} missing/duplicate FPS slot: ${JSON.stringify(state)}`);
      if (!state.slotType.split(",").includes("FLOAT") || !state.slotType.split(",").includes("INT")) throw new Error(`${label} incompatible slot type`);
    }
    for (const label of ["repairedConnected", "cloned", "restored"]) {
      if (result[label].value !== 29.97) throw new Error(`${label} lost FPS value`);
    }
    if (result.socketless.value !== 23.976) throw new Error("Socketless workflow lost FPS value");
    console.log("PASS: FPS widget + FLOAT/INT socket; named/array/socketless workflows; linked configure, clone and graph roundtrip", JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
