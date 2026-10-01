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

      const inspect = (node) => {
        const names = node.widgets.map((widget) => widget.name);
        const widget = node.widgets.find((item) => item.name === "frame_rate");
        return { names, value: widget?.value, type: widget?.type };
      };
      return { named: inspect(named), legacy: inspect(legacy) };
    });

    for (const [label, state, expected] of [["named", result.named, 12], ["legacy", result.legacy, 15]]) {
      if (state.value !== expected || state.type !== "VHS.ANNOTATED") throw new Error(`${label} value/type: ${JSON.stringify(state)}`);
      if (state.names.indexOf("frame_rate") < 0 || state.names.indexOf("frame_rate") > state.names.indexOf("loop_count")) {
        throw new Error(`${label} order: ${JSON.stringify(state.names)}`);
      }
    }
    console.log("PASS: Video Combine V2 restores missing frame_rate from named and legacy workflow values", JSON.stringify(result));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
