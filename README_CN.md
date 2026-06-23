# ComfyUI-FeiHou-Toolbox

ComfyUI 自定义节点工具箱，主要围绕多图参考、SAM3/SAM3.1 人物抠图拼接、SCAIL-2 遮罩处理、图像批次处理、布尔值传递，以及工作流分组切换进行扩展。

当前版本为 **v2.4**。
其中 **多参图像手动拼接** 的最新版本为 **v2.2.2**。

<p align="right">
  <a href="README.md">English Version</a>
</p>

---

## 安装

### ComfyUI Manager 安装

在 ComfyUI Manager 中搜索 `ComfyUI-FeiHou-Toolbox`，安装后重启 ComfyUI。

### 手动安装

进入 ComfyUI 的 `custom_nodes` 目录，执行：

```bash
git clone https://github.com/FX-FeiHou/ComfyUI-FeiHou-Toolbox.git
```

安装或更新后建议重启 ComfyUI，并强制刷新浏览器页面。

---

## 节点概览

节点显示标题会跟随当前 ComfyUI 界面语言自动切换。本文档展示中文标题。

| 节点标题 | 节点注册名 | 版本 |
| --- | --- | --- |
| 创建 SCAIL-2 彩色遮罩 V2 | `SCAIL2ColoredMaskV2` | v2.2 |
| 多参图像自动拼接 | `AutoRefCollage` | v1.0 |
| 多参图像手动拼接 | `ManualRefCollage` | v2.2.2 |
| 切换 V2 | `ComfySwitchNodeV2` | v2.0 |
| 反转布尔值 | `InvertBoolean` | v2.3 |
| 图像组合批次（多重）V2 | `ImageBatchMultiV2` | v2.4 |
| 多框忽略并切换 | `FastGroupsBypassSwitch` | v2.0 |

### 创建 SCAIL-2 彩色遮罩 V2

基于 ComfyUI 原版 SCAIL-2 彩色遮罩节点扩展，主要用于多图参考流程中的遮罩拆分、传递和批量处理。

`prefix_mask_mode` 支持：

- `Multi Image Single Color`：输出批次中每张图都是单色，颜色与 `reference_image_mask` 接口当前前景颜色保持一致。
- `Multi Image Multi Color`：输出批次中每张图都按节点对象调色板规则输出彩色遮罩。
- `Single Image Multi Color`：输出批次图按批次顺序分别为蓝、红、绿、洋红、青，超过 5 张后循环。

### 多参图像自动拼接（AutoRefCollage）

自动读取多张参考图，通过 SAM3/SAM3.1 抠出人物，并生成一张多人物参考拼图，适合快速制作多人参考图。

### 多参图像手动拼接（v2.2.2）

手动拼图节点。可将多张参考图经过 SAM3/SAM3.1 抠图后载入拼图画布，用户可以手动调整人物位置和大小，再由节点输出最终拼好的图。

### 切换 V2

Switch 节点的改版，用于在两条路径之间切换，并减少未启用分支对工作流运行的影响。

### 反转布尔值

只有一个输入和一个输出的布尔值反转节点。可接收 `PrimitiveBoolean` 输出的 `BOOLEAN`，并将 `true` 反转为 `false`，将 `false` 反转为 `true`。

### 图像组合批次（多重）V2

基于 KJNodes `ImageBatchMulti` 复制改造的图像批次组合节点。保留 `inputcount` 和 `Update inputs` 的动态接口流程，但未接入或被屏蔽的图像输入会被跳过，不再补黑色占位图。如果所有图像接口都没有可用输入，则不输出图像。

### 多框忽略并切换（v2.0）

分组忽略与切换节点。可绑定两个 ComfyUI Group，在两个分组之间快速切换，同时切换对应的数据输出。

---

## 版本记录

### v2.5

- 优化 `AutoRefCollage（多参图像自动拼接）` 和 `ManualRefCollage（多参图像手动拼接）` 的 SAM3/SAM3.1 抠图显存占用。
- 为 CLIP 提示词编码和 SAM3 推理增加 `torch.no_grad()`，避免载入图片预览和工作流执行时保留推理计算图。
- 降低提示词命中后的二次精修显存峰值：精修前只保留最佳 mask/box，并避免裁剪前把整张原图复制到 GPU。

### v2.4

- 新增 `ImageBatchMultiV2（图像组合批次（多重）V2）` 节点，基于 KJNodes `ImageBatchMulti` 复制改造。
- 保留原节点 `inputcount` 和 `Update inputs` 的动态接口流程。
- 调整缺失输入处理：未接入或被屏蔽的图像输入会被跳过，不再自动补黑图。
- 如果所有图像接口都没有可用输入，则节点不输出图像。

### v2.3

- 新增 `InvertBoolean（反转布尔值）` 节点，只有一个布尔输入和一个布尔输出。
- 兼容 `PrimitiveBoolean` 输出链路，可将 `true` 反转为 `false`，将 `false` 反转为 `true`。

### v2.2.2

- 调整 `ManualRefCollage（多参图像手动拼接）` 的尺寸应用逻辑：只有点击 `应用尺寸` 时才读取当前 `width` / `height` 输入并改变手动画布尺寸。
- `ManualRefCollage` 不再在节点创建、连接变化或点击 `载入图片` 时自动应用外接宽高，避免 KJNodes `Set` / `Get` 变量链还未准备好时被提前读取。
- 增加对 KJNodes `Set_变量名` / `Get_变量名` 宽高传递方式的兼容；点击 `应用尺寸` 时会尝试找到同名 `Set` 节点并沿其输入读取数值。

### v2.2.1

- 修复 `ManualRefCollage（多参图像手动拼接）` 在 `width` / `height` 外接输入时，前端手动画布和后端执行输出无法正确获取外接尺寸的问题。
- 手动拼图现在会优先从外接宽高输入读取尺寸，读取不到时才回退到节点自身宽高控件。

### v2.2

- 更新 `Create SCAIL-2 Colored Mask V2` 的 `prefix_mask_mode` 逻辑。
- `Multi Image Single Color` 输出批次中每张图都是单色，颜色与 `reference_image_mask` 接口当前前景颜色保持一致。
- 新增 `Multi Image Multi Color`，用于让输出批次中的每张图都按节点对象调色板规则生成彩色遮罩。
- `Single Image Multi Color` 输出批次图按批次顺序分别为蓝、红、绿、洋红、青，超过 5 张后循环。

### v2.1

- 修复 `ManualRefCollage（多参图像手动拼接）` 载入图片预览时仍读取已忽略/跳过的输入图问题。
- 修复手动拼图执行时已忽略/跳过的图片输入仍参与拼图的问题。
- 修复外接 `width` / `height` 时被旧 `layout_json` 尺寸覆盖的问题。

### v2.0

- 新增 `FastGroupsBypassSwitch（多框忽略并切换）` 节点。
- 支持两个 ComfyUI Group 之间的启用、忽略和输出切换。
- UI 参考 rgthree 的 Fast Groups Bypasser 风格，适合大型分组工作流快速切换。

### v1.5

- 完成 `ManualRefCollage（多参图像手动拼接）` 节点。
- 支持最多 5 张参考图的 SAM3/SAM3.1 抠图与手动排版。
- 支持视频首帧作为构图参考背景，最终输出仍为黑底或白底拼图。

### v1.0

- 首版发布。
- 新增 `Create SCAIL-2 Colored Mask V2`。
- 新增 `多参图像自动拼接（AutoRefCollage）`。
