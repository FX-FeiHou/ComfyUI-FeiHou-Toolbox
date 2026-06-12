# ComfyUI-FeiHou-Toolbox

<p align="right">
  <a href="README.md">🇬🇧 English Version</a>
</p>

专为 ComfyUI 打造的自定义节点工具箱。

---

## 🌟 核心特性
* **Scail2 多图参考专项优化：** 专为解决 Scail2 多图参考工作流中的数据传递与画面排版痛点而设计。
* **精简数据链路：** 扩展并打通核心接口，轻松应对多路追踪数据与遮罩资产的整合输出。
* **高扩展性架构：** 采用工具箱式结构设计，未来将持续收录并迭代其他实用的自定义功能节点。

## ⚙️ 安装指南

### 方法一：通过 ComfyUI Manager 安装（推荐）
1. 在 ComfyUI Manager 中搜索 `ComfyUI-FeiHou-Toolbox`。
2. 点击 **Install** 安装。
3. 重启 ComfyUI。

### 方法二：手动 Git 克隆
进入你的 ComfyUI `custom_nodes` 根目录下，打开终端运行：

**git clone https://github.com/FX-FeiHou/ComfyUI-FeiHou-Toolbox.git**

重启 ComfyUI 并硬刷新浏览器页面 (Ctrl + F5)。

## 🛠️ 节点列表

### 1. Create SCAIL-2 Colored Mask V2
在官方原版 `Create SCAIL-2 Colored Mask` 节点的基础上进行了深度魔改与增强。
* **新增接口：** 扩展了输入的 `prefix_track_data` 和输出的 `prefix_image_mask` 接口，极大方便了多图参考流中的遮罩数据传递与分流。
* **性能优化：** 优化了底层绘制逻辑，优先调用 GPU 进行遮罩渲染，大幅提升出图响应速度。

### 2. AutoRefCollage（多参图像自动拼接）
专为多人遮罩场景打造的多参考图自动拼接工具。
* **核心功能：** 能够将 4 张独立的参考图自动拼接成一张合集网格图。
* **应用场景：** 非常适合在制作“多人遮罩”时，将多位角色的参考图预先整合，方便在单个 Scail2 画布中进行高效遮罩处理。

## 📅 更新日志
* **v1.0.0**
  * 工具箱首发，包含专注于 Scail2 多图参考流的 `Create SCAIL-2 Colored Mask V2` 和 `AutoRefCollage` 两个核心节点。