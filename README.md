# ComfyUI-FeiHou-Toolbox

<p align="right">
  <a href="README_CN.md">🇨🇳 中文说明 (Chinese)</a>
</p>

A custom node toolbox for ComfyUI. 

---

## 🌟 Key Features
* **Multi-Ref Scail2 Optimization:** Tailored specifically to solve data routing and composition challenges in multi-image reference Scail2 workflows.
* **Streamlined Data Pipelines:** Enhances interface connectivity to handle multi-source tracking and mask assets with ease.
* **Extensible Architecture:** Built as a scalable toolbox, ready to welcome diverse feature modules in upcoming releases.

## ⚙️ Installation

### Method 1: Via ComfyUI Manager (Recommended)
1. Search for `ComfyUI-FeiHou-Toolbox` in ComfyUI Manager.
2. Click **Install**.
3. Restart ComfyUI.

### Method 2: Manual Git Clone
Navigate to your ComfyUI `custom_nodes` directory and run:

**git clone https://github.com/FX-FeiHou/ComfyUI-FeiHou-Toolbox.git**

Restart ComfyUI and refresh your browser page (Ctrl + F5).

## 🛠️ Nodes Overview

### 1. Create SCAIL-2 Colored Mask V2
Modified from the official `Create SCAIL-2 Colored Mask` node to significantly enhance usability in multi-image reference scenarios.
* **New Interfaces:** Added `prefix_track_data` input and `prefix_image_mask` output ports to facilitate seamless mask data routing.
* **Execution Boost:** Optimizes the underlying drawing logic by utilizing the GPU preferentially to accelerate mask generation.

### 2. AutoRefCollage
An automated multi-reference image collaging utility designed for multi-person character masking.
* **Core Function:** Automatically stitches 4 separate input reference images into a single consolidated image grid.
* **Scail2 Synergy:** Perfect for setting up and generating multi-person masks efficiently within a single canvas area.

## 📅 Changelog
* **v1.0.0**
  * Repository launched with Scail2 multi-ref optimized nodes: `Create SCAIL-2 Colored Mask V2` and `AutoRefCollage`.