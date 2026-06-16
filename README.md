# ComfyUI-FeiHou-Toolbox

A ComfyUI custom node toolbox focused on multi-image references, SAM3/SAM3.1 person cutouts, SCAIL-2 mask workflows, and group-based workflow switching.

Current version: **v2.2.2**.
The latest version of **ManualRefCollage** is **v2.2.2**.

<p align="right">
  <a href="README_CN.md">中文说明</a>
</p>

---

## Installation

### ComfyUI Manager

Search for `ComfyUI-FeiHou-Toolbox` in ComfyUI Manager, install it, then restart ComfyUI.

### Manual Install

Open your ComfyUI `custom_nodes` directory and run:

```bash
git clone https://github.com/FX-FeiHou/ComfyUI-FeiHou-Toolbox.git
```

After installing or updating, restart ComfyUI and hard-refresh the browser page.

---

## Nodes Overview

| Node ID | Display Name | Version |
| --- | --- | --- |
| `SCAIL2ColoredMaskV2` | Create SCAIL-2 Colored Mask V2 | v2.2 |
| `AutoRefCollage` | 多参图像自动拼接 | v1.0 |
| `ManualRefCollage` | 多参图像手动拼接 | v2.2.2 |
| `ComfySwitchNodeV2` | Switch V2 | v2.0 |
| `FastGroupsBypassSwitch` | 多框忽略并切换 | v2.0 |

### Create SCAIL-2 Colored Mask V2

An enhanced version of ComfyUI's original SCAIL-2 colored mask node, built for mask routing, separation, and batch handling in multi-reference workflows.

`prefix_mask_mode` supports:

- `Multi Image Single Color`: each output batch image is single-color, matching the current `reference_image_mask` foreground color.
- `Multi Image Multi Color`: each output batch image uses the node's object color palette rule.
- `Single Image Multi Color`: output batch images use batch-order colors: blue, red, green, magenta, cyan, then loop after 5 images.

### AutoRefCollage

Automatically uses SAM3/SAM3.1 to cut people out from multiple reference images and compose them into a single multi-person reference collage.

### ManualRefCollage (多参图像手动拼接, v2.2.2)

A manual collage node that loads SAM3/SAM3.1 cutouts onto an editable canvas, allowing users to adjust position and scale before outputting the final composed image.

### Switch V2

A revised switch node for toggling between two workflow paths while reducing issues caused by inactive branches.

### FastGroupsBypassSwitch (多框忽略并切换, v2.0)

A group bypass and switch node that binds two ComfyUI Groups, switches which group is active, bypasses the inactive group, and outputs the corresponding input.

---

## Changelog

### v2.2.2

- Changed `ManualRefCollage` size handling so the manual canvas reads and applies current `width` / `height` inputs only when `应用尺寸` is clicked.
- `ManualRefCollage` no longer auto-applies linked width/height during node creation, connection changes, or `载入图片`, avoiding early reads before KJNodes `Set` / `Get` variable chains are ready.
- Added compatibility for KJNodes-style `Set_variable` / `Get_variable` width and height routing; clicking `应用尺寸` now attempts to resolve the matching `Set` node and read the value from its input chain.

### v2.2.1

- Fixed `ManualRefCollage` not correctly reading externally connected `width` / `height` inputs in both the frontend manual canvas and backend execution.
- Manual collage now prioritizes linked width/height inputs and falls back to the node's own width/height widgets only when linked values cannot be resolved.

### v2.2

- Updated `Create SCAIL-2 Colored Mask V2` `prefix_mask_mode` behavior.
- `Multi Image Single Color` renders every output batch image as a single color matching the current `reference_image_mask` foreground color.
- Added `Multi Image Multi Color` for rendering every output batch image with the node's object color palette rule.
- `Single Image Multi Color` renders output batch images with batch-order colors: blue, red, green, magenta, cyan, then loops after 5 images.

### v2.1

- Fixed `ManualRefCollage` preview loading images from ignored/bypassed inputs.
- Fixed ignored/bypassed image inputs still being included during manual collage execution.
- Fixed externally connected `width` / `height` being overridden by stale `layout_json` dimensions.

### v2.0

- Added `FastGroupsBypassSwitch` (`多框忽略并切换`).
- Supports enabling, bypassing, and output switching between two ComfyUI Groups.
- UI follows the rgthree Fast Groups Bypasser style for large grouped workflows.

### v1.5

- Finalized `ManualRefCollage` (`多参图像手动拼接`).
- Supports SAM3/SAM3.1 cutouts and manual layout for up to 5 reference images.
- Supports using the first video frame as a composition reference while keeping the final output on a black or white background.

### v1.0

- Initial release.
- Added `Create SCAIL-2 Colored Mask V2`.
- Added `AutoRefCollage`.
