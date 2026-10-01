# ComfyUI-FeiHou-Toolbox

## 花果山Ai灵境坊

- 网站 / API 服务：[api.fei-hou.net](https://api.fei-hou.net/)
- Windows 客户端下载：[GitHub](https://github.com/FX-FeiHou/FeiHou-Ai-Studio/releases/latest) · [夸克网盘](https://pan.quark.cn/s/327190b9484c)。首次使用请选择 `FeiHou-Ai-Studio-Win-1.1.4-full.zip` 完整包，不要选择增量更新包或 Source code；已有用户优先通过启动器更新。
- 范例工作流：[API 生图与视频合并范例](workflows/FeiHou_API_Image%26Video_example.json)。其中的文本显示和分组开关分别需要 ComfyUI-Custom-Scripts、rgthree-comfy；API 节点本身不依赖这两个包。

ComfyUI 自定义节点工具箱，主要围绕多图参考、SAM3/SAM3.1 人物抠图拼接、SCAIL-2 遮罩处理、图像批次处理、布尔值传递，以及工作流分组切换进行扩展。

当前版本为 **v2.10.3**。
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

### FeiHou API 媒体节点

`FeiHou-API Images` 和 `FeiHou-API Video` 接入 `https://api.fei-hou.net`。填写 API Key、刷新模型并设置参数后运行。

媒体载入已独立为 `FeiHou-API Media` 节点，直接采用 Easy-H3 的媒体区样式，支持 9 张图片、3 个视频、3 个音频，以及替换、删除、同类拖动排序和音频区间截取。将其“媒体”输出连接至 API 生成节点，在生成节点提示词中输入 `@` 即可选择已载入的素材。复制节点和保存工作流会保留媒体记录；媒体文件保存在当前 ComfyUI 输入目录，工作流 JSON 本身不包含文件内容。

`媒体输入` 接口也兼容原生 IMAGE（批次）、VIDEO 或 AUDIO；使用独立载入节点时提供可视化 `@` 选择。模型的实际素材限制仍生效：例如 Seedance 多模态需选择 `-multi`，`-t2v` 不接受参考素材，生图接口不接收视频和音频。API Key 会随普通节点控件保存在工作流中，分享前请清空。

范例工作流：[API 生图与视频合并范例](workflows/FeiHou_API_Image%26Video_example.json)。

节点显示标题会跟随当前 ComfyUI 界面语言自动切换。本文档展示中文标题。

| 节点标题 | 节点注册名 | 版本 |
| --- | --- | --- |
| 创建 SCAIL-2 彩色遮罩 V2 | `SCAIL2ColoredMaskV2` | v2.6 |
| 多参图像自动拼接 | `AutoRefCollage` | v1.0 |
| 多参图像手动拼接 | `ManualRefCollage` | v2.2.2 |
| 切换 V2 | `ComfySwitchNodeV2` | v2.0 |
| 反转布尔值 | `InvertBoolean` | v2.3 |
| 图像组合批次（多重）V2 | `ImageBatchMultiV2` | v2.4 |
| 多框忽略并切换 | `FastGroupsBypassSwitch` | v2.0 |
| 随机种子噪波 | `RandomSeedNoise` | v2.8 |
| Video Combine 🎥🅥🅗🅢 V2 | `VideoCombineV2` | v2.9 |
| FeiHou-视频预览 | `FeiHouVideoPreview` | v2.9.5 |
| FeiHou-API Images | `FeiHouApiImage` | v2.10.0 |
| FeiHou-API Video | `FeiHouApiVideo` | v2.10.0 |
| FeiHou-API Media | `FeiHouApiMediaLoader` | v2.10.0 |

- **FeiHou-视频预览**：预览生成或本地载入的视频，支持循环播放与预览控制。
- **FeiHou-API Images**：API 生图，支持模型选择、分辨率、画面比例和媒体参考。
- **FeiHou-API Video**：API 生视频，按模型提供生成参数，输出视频、视频链接和尾帧图片。
- **FeiHou-API Media**：独立媒体载入，最多支持 9 图、3 视频、3 音频，通过连线在提示词中 `@` 引用。

### 创建 SCAIL-2 彩色遮罩 V2

基于 ComfyUI 原版 SCAIL-2 彩色遮罩节点扩展，主要用于多图参考流程中的遮罩拆分、传递和批量处理。

`prefix_mask_mode` 支持：

- `Multi Image Single Color`：输出批次中每张图都是单色，颜色与 `reference_image_mask` 接口当前前景颜色保持一致。
- `Multi Image Multi Color`：输出批次中每张图都按节点对象调色板规则输出彩色遮罩。
- `Single Image Multi Color`：输出批次图按批次顺序分别为蓝、红、绿、洋红、青，超过 5 张后循环。

`render_device` 支持：

- `gpu`：在显卡上渲染遮罩，速度更快，但会占用显存。
- `cpu`：将遮罩渲染卸载到系统内存，显著降低显存占用，但处理速度较慢。

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

### v2.10.3

- 修复新版 ComfyUI 前端载入旧工作流时，`Video Combine 🎥🅥🅗🅢 V2` 节点帧率控件消失的问题。
- 兼容命名字段和旧版位置数组，并尽量恢复工作流中原来保存的帧率。

### v2.10.2

- 拖入 FeiHou-视频预览节点的本地视频直接使用浏览器临时地址预览，不上传、不导入视频内嵌工作流。节点外的拖放保留 ComfyUI 原行为；刷新页面后需重新选择本地视频。

### v2.10.1

- 修复 ComfyUI 0.33.1 缺少核心视频预览函数导致整个节点包无法加载的问题，改用包内预览实现并兼容旧版保存接口。
- 7 项本地测试通过；尚未在用户云电脑实测。

### v2.10.0

- API Video 新增尾帧 IMAGE 输出：优先使用 API 尾帧图片，否则从视频提取最后一帧；不额外保存 PNG。关闭“请求返回尾帧”也可使用此输出。

- 新增 FeiHou-API Images、FeiHou-API Video 和独立 FeiHou-API Media，接入 api.fei-hou.net。
- 支持模型刷新、模型参数、9 图/3 视频/3 音频、原生提示词框的 @ 引用和音频截取。
- 采用 Easy-H3 媒体区样式，修正边距、动态布局、隐藏记录和底部缩放；支持旧工作流迁移。
- 更新中英 i18n 和两份范例工作流。

### v2.9.4

- 将 Video Combine V2 的全部界面控件改为带后端默认值的可选输入。即使前端未提交控件值，也不会再因 `Required input is missing: loop_count` 被工作流校验拦截。

### v2.9.3

- 将原版 VHS 数值控件一并内置到 Video Combine V2；未安装 VideoHelperSuite 时，`frame_rate` 与 `loop_count` 仍会显示为正常控件，不再变成必连插口。

### v2.9.2

- 修复 Video Combine V2 的控件被错误判定为“必须连接”的问题（包括 `loop_count`）。
- 内置完整 VideoHelperSuite Video Combine 后端实现，Video Combine V2 不再依赖单独安装 ComfyUI-VideoHelperSuite。
- 保留原版完整格式、批处理、VAE、音频和预览逻辑；视频文件写入工作流元数据，接入音频时仅保留一份最终视频且不保存首帧 PNG。

### v2.9.1

- Video Combine V2 恢复原版 VideoHelperSuite Video Combine 的执行、预览状态恢复、批次队列与 VHS 文件名输出逻辑。
- Video Combine V2 仅保留一份带音频的最终视频，写入 ComfyUI 工作流元数据，且不保存原版首帧 PNG 附件。

### v2.9.0

- 新增 `Video Combine 🎥🅥🅗🅢 V2`：完整沿用 VideoHelperSuite Video Combine 的界面、格式预设、VAE/LATENT 处理、日期前缀和预览逻辑。
- 接入音频后只写出一个最终视频文件；该文件同时包含视频流、音频流，以及 ComfyUI 提示词和工作流元数据。
- 补全 VideoHelperSuite 的全部格式下拉与随格式变化的动态参数；预览自动静音播放，鼠标悬停时播放声音。

### v2.8

- 新增 `随机种子噪波`：采用 rgthree 风格随机种子操作，输出可供 `SamplerCustomAdvanced` 使用的标准 `NOISE`。

### v2.6

- 修改渲染设备为 `gpu` 和 `cpu` 两个选项，默认使用 `gpu`；如果长视频爆显存，请手动改为 `cpu`。

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
