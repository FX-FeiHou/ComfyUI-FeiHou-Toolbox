# ComfyUI-FeiHou-Toolbox

ComfyUI 自定义节点工具箱，主要围绕多图参考、SAM3/SAM3.1 人物抠图拼接、SCAIL-2 遮罩处理，以及工作流分组切换进行扩展。

当前版本为 **v2.0**。  
其中 **多参图像手动拼接** 的最后版本为 **v1.5**。

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

| 节点注册名 | 节点显示名 | 版本 |
| --- | --- | --- |
| `SCAIL2ColoredMaskV2` | Create SCAIL-2 Colored Mask V2 | v1.0 |
| `AutoRefCollage` | 多参图像自动拼接 | v1.0 |
| `ManualRefCollage` | 多参图像手动拼接 | v1.5 |
| `ComfySwitchNodeV2` | Switch V2 | v2.0 |
| `FastGroupsBypassSwitch` | 多框忽略并切换 | v2.0 |

### Create SCAIL-2 Colored Mask V2

基于 ComfyUI 原版 SCAIL-2 彩色遮罩节点扩展，主要用于多图参考流程中的遮罩拆分、传递和批量处理。

### 多参图像自动拼接（AutoRefCollage）

自动读取多张参考图，通过 SAM3/SAM3.1 抠出人物，并生成一张多人物参考拼图，适合快速制作多人参考图。

### ManualRefCollage（多参图像手动拼接，v1.5）

手动拼图节点。可将多张参考图经过 SAM3/SAM3.1 抠图后载入拼图画布，用户可以手动调整人物位置和大小，再由节点输出最终拼好的图。

### Switch V2

Switch 节点的改版，用于在两条路径之间切换，并减少未启用分支对工作流运行的影响。

### FastGroupsBypassSwitch（多框忽略并切换，v2.0）

分组忽略与切换节点。可绑定两个 ComfyUI Group，在两个分组之间快速切换，同时切换对应的数据输出。

---

## 版本记录

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
