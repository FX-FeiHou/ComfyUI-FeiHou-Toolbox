"""FeiHou Toolbox custom nodes.

Copyright (C) 2026 FeiHou Toolbox contributors.

SPDX-License-Identifier: GPL-3.0

Create SCAIL-2 Colored Mask V2 is a non-conflicting copy of ComfyUI's
built-in Create SCAIL-2 Colored Mask node with an extra prefix image mask
output.

Modified from ComfyUI's built-in SCAIL2ColoredMask node.
Modifications:
- Added prefix_image_mask output for prefix image batches.
- Added configurable torch render device handling.
- Fixed replacement_mode background handling for generated masks.
- Added warnings when prefix track data contains no usable mask.

AutoRefCollage is original code for this toolbox. It uses ComfyUI's SAM3
model interfaces to extract people from multiple reference images and compose
them into portrait, square, or landscape collages.
"""

import base64
import json
import logging
import os
import re
from io import BytesIO

from typing_extensions import override

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps, ImageSequence
from aiohttp import web

import comfy.model_management
import comfy.sd
import comfy.utils
import folder_paths
import nodes as comfy_nodes
from comfy_api.latest import ComfyExtension, io
from comfy.ldm.sam3.tracker import unpack_masks

try:
    from server import PromptServer
except Exception:  # pragma: no cover
    PromptServer = None


SAM3TrackData = io.Custom("SAM3_TRACK_DATA")
MISSING = object()
WEB_DIRECTORY = "./js"

LOGGER = logging.getLogger(__name__)
PREVIEW_CHECKPOINT_CACHE = {"name": None, "model": None, "clip": None}
MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
    ".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv",
}
INACTIVE_NODE_MODES = {2, 4}


# Model was trained on these exact colors; deviating degrades multi-identity quality.
DEFAULT_PALETTE = [
    (0.0, 0.0, 1.0),  # Blue
    (1.0, 0.0, 0.0),  # Red
    (0.0, 1.0, 0.0),  # Green
    (1.0, 0.0, 1.0),  # Magenta
    (0.0, 1.0, 1.0),  # Cyan
    (1.0, 1.0, 0.0),  # Yellow
]
PREFIX_BATCH_PALETTE = DEFAULT_PALETTE[:5]


def _first_batch_frame(image):
    if image is None:
        return None
    if not isinstance(image, torch.Tensor):
        return None
    if image.ndim != 4:
        return None
    if image.shape[0] < 1 or image.shape[1] < 1 or image.shape[2] < 1 or image.shape[3] < 3:
        return None
    return image[:1, ..., :3]


def _load_input_image_from_name(image_name):
    image_path = _resolve_media_filepath(image_name)
    img = Image.open(image_path)
    frames = []
    for frame in ImageSequence.Iterator(img):
        frame = ImageOps.exif_transpose(frame).convert("RGB")
        frames.append(torch.from_numpy(np.array(frame).astype(np.float32) / 255.0)[None, ...])
        break
    if not frames:
        raise ValueError(f"Failed to load image: {image_name}")
    return frames[0]


def _resolve_media_filepath(media_name):
    name = str(media_name or "").strip()
    if not name:
        raise ValueError("Missing media name.")
    try:
        resolved = folder_paths.get_annotated_filepath(name)
        if os.path.exists(resolved):
            return resolved
    except Exception:
        pass
    if os.path.exists(name):
        return name
    input_dir = getattr(folder_paths, "get_input_directory", lambda: "")()
    candidate = os.path.join(input_dir, os.path.basename(name)) if input_dir else ""
    if candidate and os.path.exists(candidate):
        return candidate
    raise FileNotFoundError(f"Media file not found: {name}")


def _tensor_rgba_to_data_url(rgb, alpha):
    rgba = torch.cat([rgb.clamp(0, 1), alpha.clamp(0, 1).unsqueeze(-1)], dim=-1)
    arr = (rgba.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    image = Image.fromarray(arr, mode="RGBA")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _tensor_rgb_to_data_url(rgb):
    arr = (rgb.clamp(0, 1).cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    if arr.ndim == 4:
        arr = arr[0]
    image = Image.fromarray(arr, mode="RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _load_media_first_frame_from_name(media_name):
    media_path = _resolve_media_filepath(media_name)
    ext = os.path.splitext(media_path)[1].lower()
    if ext in {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}:
        try:
            import cv2
            cap = cv2.VideoCapture(media_path)
            try:
                ok, frame = cap.read()
            finally:
                cap.release()
            if ok and frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return torch.from_numpy(frame.astype(np.float32) / 255.0)[None, ...]
        except Exception:
            pass
        try:
            import imageio.v3 as iio
            frame = iio.imread(media_path, index=0)
            if frame is not None:
                if frame.ndim == 2:
                    frame = np.stack([frame, frame, frame], axis=-1)
                return torch.from_numpy(frame[..., :3].astype(np.float32) / 255.0)[None, ...]
        except Exception as exc:  # pragma: no cover
            raise ValueError("无法读取视频首帧，请检查视频文件或相关依赖。") from exc
        raise ValueError(f"Failed to load video first frame: {media_name}")
    return _load_input_image_from_name(media_name)


def _resolve_prompt_node(prompt, node_id):
    if not isinstance(prompt, dict):
        return None
    return prompt.get(str(node_id)) or prompt.get(node_id)


def _extract_media_name_from_value(value):
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        lower = stripped.lower()
        for ext in MEDIA_EXTENSIONS:
            if lower.endswith(ext) or f"{ext} " in lower or f"{ext}[" in lower:
                return stripped
        return ""
    if isinstance(value, dict):
        for item in value.values():
            found = _extract_media_name_from_value(item)
            if found:
                return found
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _extract_media_name_from_value(item)
            if found:
                return found
        return ""
    return ""


def _normalize_media_name(value):
    extracted = _extract_media_name_from_value(value)
    if extracted:
        return extracted.strip()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            _resolve_media_filepath(stripped)
            return stripped
        except Exception:
            return ""
    return ""


def _iter_upstream_node_ids(prompt, value):
    if isinstance(value, list) and len(value) == 2 and _resolve_prompt_node(prompt, value[0]) is not None:
        yield value[0]
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_upstream_node_ids(prompt, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_upstream_node_ids(prompt, item)


def _resolve_media_name_from_node(prompt, node_id, visited):
    source = _resolve_prompt_node(prompt, node_id)
    node_key = str(node_id)
    if not isinstance(source, dict) or node_key in visited:
        return ""
    visited.add(node_key)
    source_inputs = source.get("inputs", {})

    for key in ("image", "video", "upload", "filename", "file", "path", "media", "video_file", "image_name"):
        found = _extract_media_name_from_value(source_inputs.get(key))
        if found:
            return found
    for value in source_inputs.values():
        found = _extract_media_name_from_value(value)
        if found:
            return found
    for value in source_inputs.values():
        for upstream_id in _iter_upstream_node_ids(prompt, value):
            found = _resolve_media_name_from_node(prompt, upstream_id, visited)
            if found:
                return found
    return ""


def _resolve_linked_media_name(prompt, node_id, input_name):
    prompt_node = _resolve_prompt_node(prompt, node_id)
    if not isinstance(prompt_node, dict):
        return ""
    link = prompt_node.get("inputs", {}).get(input_name)
    if not isinstance(link, list) or len(link) != 2:
        return ""
    return _resolve_media_name_from_node(prompt, link[0], set())


def _bool_enabled(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "disabled", "bypassed", "skip", "skipped"}
    return default


def _clamp_manual_dimension(value, fallback):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(fallback)
    return max(64, min(8192, parsed))


def _workflow_node_by_id(workflow, node_id):
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not isinstance(nodes, list):
        return {}
    wanted = str(node_id)
    for node in nodes:
        if isinstance(node, dict) and str(node.get("id")) == wanted:
            return node
    return {}


def _workflow_link_origin_id(workflow, link_id):
    links = workflow.get("links") if isinstance(workflow, dict) else None
    if not isinstance(links, list):
        return None
    wanted = str(link_id)
    for link in links:
        if isinstance(link, dict):
            current_id = link.get("id", link.get("link_id"))
            if str(current_id) == wanted:
                return link.get("origin_id", link.get("source_id"))
        elif isinstance(link, (list, tuple)) and len(link) >= 2 and str(link[0]) == wanted:
            return link[1]
    return None


def _workflow_input_link_id(node, input_name):
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if isinstance(inputs, list):
        for slot in inputs:
            if isinstance(slot, dict) and slot.get("name") == input_name:
                return slot.get("link")
    return None


def _workflow_node_is_inactive(node):
    if not isinstance(node, dict):
        return False
    try:
        mode = int(node.get("mode", 0))
    except (TypeError, ValueError):
        return False
    return mode in INACTIVE_NODE_MODES


def _workflow_input_is_active(extra_pnginfo, unique_id, input_name):
    workflow = (extra_pnginfo or {}).get("workflow") if isinstance(extra_pnginfo, dict) else None
    if not isinstance(workflow, dict):
        return True
    current = _workflow_node_by_id(workflow, unique_id)
    link_id = _workflow_input_link_id(current, input_name)
    if link_id is None:
        return True
    origin_id = _workflow_link_origin_id(workflow, link_id)
    if origin_id is None:
        return True
    return not _workflow_node_is_inactive(_workflow_node_by_id(workflow, origin_id))


def _numeric_from_value(value, preferred_names=()):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    if isinstance(value, dict):
        for name in preferred_names:
            if name in value:
                found = _numeric_from_value(value.get(name), preferred_names)
                if found is not None:
                    return found
        if "value" in value:
            found = _numeric_from_value(value.get("value"), preferred_names)
            if found is not None:
                return found
        for item in value.values():
            found = _numeric_from_value(item, preferred_names)
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _numeric_from_value(item, preferred_names)
            if found is not None:
                return found
    return None


def _numeric_names_for_input(input_name):
    if input_name == "width":
        return ("width", "w", "value", "number", "int", "integer", "宽度", "宽")
    if input_name == "height":
        return ("height", "h", "value", "number", "int", "integer", "高度", "高")
    return ("value", input_name, "number", "int", "integer")


def _normalize_variable_key(value):
    if value is None:
        return ""
    text = str(value).strip()
    for prefix in ("get", "set", "获取", "读取", "设置", "写入"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    for char in (" ", "\t", "_", "-", ":", "："):
        text = text.replace(char, "")
    return text.lower()


def _variable_mode_matches(value, mode):
    if not mode:
        return True
    text = str(value or "").lower()
    if mode == "get":
        return text in {"get", "获取", "读取"}
    if mode == "set":
        return text in {"set", "设置", "写入"}
    return text == mode


def _node_text_fields(node):
    if not isinstance(node, dict):
        return ()
    return (
        node.get("title"),
        node.get("type"),
        node.get("class_type"),
        node.get("display_name"),
    )


def _workflow_node_looks_like_variable_node(node, mode):
    if mode == "set":
        pattern = r"(^|[\s_:\-：])(set|设置|写入)(?=$|[\s_:\-：])"
    else:
        pattern = r"(^|[\s_:\-：])(get|获取|读取)(?=$|[\s_:\-：])"
    for value in _node_text_fields(node):
        text = str(value or "").lower()
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _workflow_collect_variable_keys(node, mode=""):
    keys = []
    field_names = {
        "key",
        "name",
        "variable",
        "variable_name",
        "var_name",
        "id",
        "label",
        "text",
        "string",
        "value",
        "变量",
        "变量名",
        "名称",
        "名字",
    }

    def add_key(value):
        key = _normalize_variable_key(value)
        if key and key not in keys:
            keys.append(key)

    for value in _node_text_fields(node):
        text = str(value or "").strip()
        match = re.search(r"(?:^|[\s_:\-：])(get|set)[\s_:\-：]+(.+)$", text, re.IGNORECASE)
        if not match:
            match = re.search(r"(?:^|[\s_:\-：])(获取|读取|设置|写入)[\s_:\-：]*(.+)$", text, re.IGNORECASE)
        if match and _variable_mode_matches(match.group(1), mode):
            add_key(match.group(2))

    widgets_values = node.get("widgets_values") if isinstance(node, dict) else None
    if isinstance(widgets_values, dict):
        for name, value in widgets_values.items():
            if str(name).lower() in field_names:
                add_key(value)
    properties = node.get("properties") if isinstance(node, dict) else None
    if isinstance(properties, dict):
        for name, value in properties.items():
            if str(name).lower() in field_names:
                add_key(value)
    return keys


def _workflow_nodes(workflow):
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    return nodes if isinstance(nodes, list) else []


def _workflow_node_own_numeric_value(node, wanted_name, preferred_only=False):
    preferred_names = _numeric_names_for_input(wanted_name)
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if isinstance(inputs, dict):
        for name in preferred_names:
            found = _numeric_from_value(inputs.get(name), preferred_names)
            if found is not None:
                return found
        if preferred_only:
            return None
        for value in inputs.values():
            found = _numeric_from_value(value, preferred_names)
            if found is not None:
                return found

    widgets_values = node.get("widgets_values") if isinstance(node, dict) else None
    if isinstance(widgets_values, dict):
        for name in preferred_names:
            found = _numeric_from_value(widgets_values.get(name), preferred_names)
            if found is not None:
                return found
        if not preferred_only:
            found = _numeric_from_value(widgets_values, preferred_names)
            if found is not None:
                return found
    elif isinstance(widgets_values, (list, tuple)) and not preferred_only:
        for value in widgets_values:
            found = _numeric_from_value(value, preferred_names)
            if found is not None:
                return found

    if not preferred_only:
        found = _numeric_from_value(node.get("properties"), preferred_names)
        if found is not None:
            return found
    return None


def _workflow_linked_input_numeric_value(workflow, node, wanted_name, visited):
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, list):
        return None
    preferred_names = _numeric_names_for_input(wanted_name)

    def slot_score(slot):
        name = str(slot.get("name", "")).lower() if isinstance(slot, dict) else ""
        if name in preferred_names:
            return 0
        if name == "value":
            return 1
        return 2

    for slot in sorted((slot for slot in inputs if isinstance(slot, dict)), key=slot_score):
        link_id = slot.get("link")
        if link_id is None:
            continue
        upstream_id = _workflow_link_origin_id(workflow, link_id)
        if upstream_id is None:
            continue
        found = _workflow_node_numeric_value(workflow, upstream_id, wanted_name, visited)
        if found is not None:
            return found
    return None


def _workflow_variable_set_numeric_value(workflow, get_node, wanted_name, visited):
    if not _workflow_node_looks_like_variable_node(get_node, "get"):
        return None
    get_keys = _workflow_collect_variable_keys(get_node, "get")
    if not get_keys:
        return None
    for candidate in _workflow_nodes(workflow):
        if not isinstance(candidate, dict) or candidate is get_node or _workflow_node_is_inactive(candidate):
            continue
        if not _workflow_node_looks_like_variable_node(candidate, "set"):
            continue
        set_keys = _workflow_collect_variable_keys(candidate, "set")
        if not any(key in get_keys for key in set_keys):
            continue
        candidate_id = str(candidate.get("id", ""))
        local_visited = set(visited)
        if candidate_id and candidate_id in local_visited:
            continue
        if candidate_id:
            local_visited.add(candidate_id)
        found = _workflow_linked_input_numeric_value(workflow, candidate, wanted_name, local_visited)
        if found is not None:
            return found
        found = _workflow_node_own_numeric_value(candidate, wanted_name)
        if found is not None:
            return found
    return None


def _workflow_node_numeric_value(workflow, node_id, wanted_name, visited):
    node = _workflow_node_by_id(workflow, node_id)
    node_key = str(node_id)
    if not isinstance(node, dict) or node_key in visited or _workflow_node_is_inactive(node):
        return None
    visited.add(node_key)

    found = _workflow_node_own_numeric_value(node, wanted_name, preferred_only=True)
    if found is not None:
        return found
    found = _workflow_variable_set_numeric_value(workflow, node, wanted_name, visited)
    if found is not None:
        return found
    found = _workflow_node_own_numeric_value(node, wanted_name)
    if found is not None:
        return found
    found = _workflow_linked_input_numeric_value(workflow, node, wanted_name, visited)
    if found is not None:
        return found
    return None


def _workflow_linked_numeric_input(extra_pnginfo, unique_id, input_name, fallback):
    workflow = (extra_pnginfo or {}).get("workflow") if isinstance(extra_pnginfo, dict) else None
    if not isinstance(workflow, dict):
        return _clamp_manual_dimension(fallback, fallback)
    current = _workflow_node_by_id(workflow, unique_id)
    link_id = _workflow_input_link_id(current, input_name)
    if link_id is None:
        return _clamp_manual_dimension(fallback, fallback)
    origin_id = _workflow_link_origin_id(workflow, link_id)
    if origin_id is None:
        return _clamp_manual_dimension(fallback, fallback)
    found = _workflow_node_numeric_value(workflow, origin_id, input_name, set())
    return _clamp_manual_dimension(found if found is not None else fallback, fallback)


def _resolve_checkpoint_from_prompt(prompt, node_id):
    prompt_node = prompt.get(str(node_id)) or prompt.get(node_id)
    if not isinstance(prompt_node, dict):
        return None
    inputs = prompt_node.get("inputs", {})
    model_link = inputs.get("model")
    if not isinstance(model_link, list) or len(model_link) != 2:
        return None
    source_id = str(model_link[0])
    source = prompt.get(source_id) or prompt.get(model_link[0])
    if not isinstance(source, dict):
        return None
    if source.get("class_type") != "CheckpointLoaderSimple":
        return None
    ckpt_name = source.get("inputs", {}).get("ckpt_name")
    return str(ckpt_name) if ckpt_name else None


def _load_preview_model_and_clip(ckpt_name):
    if not ckpt_name:
        raise ValueError("Missing checkpoint name for SAM3 preview.")
    cached_name = PREVIEW_CHECKPOINT_CACHE["name"]
    if cached_name == ckpt_name and PREVIEW_CHECKPOINT_CACHE["model"] is not None and PREVIEW_CHECKPOINT_CACHE["clip"] is not None:
        return PREVIEW_CHECKPOINT_CACHE["model"], PREVIEW_CHECKPOINT_CACHE["clip"]
    ckpt_path = folder_paths.get_full_path_or_raise("checkpoints", ckpt_name)
    model, clip, _vae, *_ = comfy.sd.load_checkpoint_guess_config(
        ckpt_path,
        output_vae=True,
        output_clip=True,
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
    )
    PREVIEW_CHECKPOINT_CACHE["name"] = ckpt_name
    PREVIEW_CHECKPOINT_CACHE["model"] = model
    PREVIEW_CHECKPOINT_CACHE["clip"] = clip
    return model, clip


def _mask_bbox(mask, pad=0):
    coords = torch.nonzero(mask > 0.5, as_tuple=False)
    if coords.numel() == 0:
        return None
    y1 = int(coords[:, 0].min().item())
    y2 = int(coords[:, 0].max().item()) + 1
    x1 = int(coords[:, 1].min().item())
    x2 = int(coords[:, 1].max().item()) + 1
    height, width = mask.shape[-2], mask.shape[-1]
    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(width, x2 + pad),
        min(height, y2 + pad),
    )


def _soften_alpha(mask, blur_radius=2):
    alpha = mask.float().unsqueeze(0).unsqueeze(0)
    if blur_radius <= 0:
        return alpha[0, 0].clamp(0, 1)
    kernel = blur_radius * 2 + 1
    alpha = F.avg_pool2d(alpha, kernel_size=kernel, stride=1, padding=blur_radius)
    return alpha[0, 0].clamp(0, 1)


def _encode_sam3_prompt(clip, prompt):
    if clip is None:
        raise ValueError("AutoRefCollage / 多参图像自动拼接: CLIP input is required for SAM3 text detection.")
    if not prompt or not prompt.strip():
        prompt = "person"
    tokens = clip.tokenize(prompt)
    with torch.no_grad():
        return clip.encode_from_tokens_scheduled(tokens)


def _extract_sam3_prompt(conditioning, device, dtype):
    cond_meta = conditioning[0][1]
    emb = conditioning[0][0].to(device=device, dtype=dtype)
    mask = cond_meta.get("attention_mask")
    if mask is not None:
        mask = mask.to(device)
    else:
        mask = torch.ones(emb.shape[0], emb.shape[1], dtype=torch.int64, device=device)
    return emb, mask


def _refine_detector_mask(sam3_model, orig_image_hwc, coarse_mask, box_xyxy, height, width, device, dtype):
    pad_frac = 0.1
    x1, y1, x2, y2 = box_xyxy.tolist()
    bw, bh = x2 - x1, y2 - y1
    cx1 = max(0, int(x1 - bw * pad_frac))
    cy1 = max(0, int(y1 - bh * pad_frac))
    cx2 = min(width, int(x2 + bw * pad_frac))
    cy2 = min(height, int(y2 + bh * pad_frac))
    if cx2 <= cx1 or cy2 <= cy1:
        return F.interpolate(
            coarse_mask.unsqueeze(0).unsqueeze(0),
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )[0, 0]

    crop = orig_image_hwc[cy1:cy2, cx1:cx2, :3]
    crop_1008 = comfy.utils.common_upscale(
        crop.unsqueeze(0).movedim(-1, 1),
        1008,
        1008,
        "bilinear",
        crop="disabled",
    )
    crop_frame = crop_1008.to(device=device, dtype=dtype)
    crop_h, crop_w = cy2 - cy1, cx2 - cx1

    mask_h, mask_w = coarse_mask.shape[-2:]
    mx1, my1 = int(cx1 / width * mask_w), int(cy1 / height * mask_h)
    mx2, my2 = int(cx2 / width * mask_w), int(cy2 / height * mask_h)
    if mx2 <= mx1 or my2 <= my1:
        return F.interpolate(
            coarse_mask.unsqueeze(0).unsqueeze(0),
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )[0, 0]

    mask_logit = coarse_mask[..., my1:my2, mx1:mx2].detach().unsqueeze(0).unsqueeze(0)
    for _ in range(2):
        coarse_input = F.interpolate(mask_logit.detach(), size=(1008, 1008), mode="bilinear", align_corners=False)
        mask_logit = sam3_model.forward_segment(crop_frame, mask_inputs=coarse_input)

    refined_crop = F.interpolate(mask_logit, size=(crop_h, crop_w), mode="bilinear", align_corners=False)
    full_mask = torch.zeros(1, 1, height, width, device=device, dtype=dtype)
    full_mask[:, :, cy1:cy2, cx1:cx2] = refined_crop
    coarse_full = F.interpolate(
        coarse_mask.unsqueeze(0).unsqueeze(0),
        size=(height, width),
        mode="bilinear",
        align_corners=False,
    )
    return torch.maximum(full_mask[0, 0], coarse_full[0, 0])


def _segment_person_with_sam3(model, image, prompt, conditioning, threshold):
    _, height, width, _ = image.shape
    comfy.model_management.load_model_gpu(model)
    device = comfy.model_management.get_torch_device()
    dtype = model.model.get_dtype()
    sam3_model = model.model.diffusion_model
    with torch.no_grad():
        text_embeddings, text_mask = _extract_sam3_prompt(conditioning, device, dtype)

        image_in = comfy.utils.common_upscale(
            image[..., :3].movedim(-1, 1),
            1008,
            1008,
            "bilinear",
            crop="disabled",
        )
        frame = image_in.to(device=device, dtype=dtype)
        results = sam3_model(
            frame,
            text_embeddings=text_embeddings,
            text_mask=text_mask,
            threshold=threshold,
            orig_size=(height, width),
        )
        scores = results["scores"][0].sigmoid()
        masks = results["masks"][0]
        boxes = results["boxes"][0]
        keep = scores > threshold
        if not keep.any():
            LOGGER.warning(
                "AutoRefCollage: SAM3 found no object for prompt %r at threshold %.2f; using background fallback.",
                prompt,
                threshold,
            )
            return _fallback_person_alpha(image).to(image.device)

        keep_scores = scores[keep]
        best_local = int(keep_scores.argmax().item())
        keep_indices = torch.nonzero(keep, as_tuple=False).flatten()
        best = int(keep_indices[best_local].item())
        coarse_mask = masks[best].detach().clone()
        box_xyxy = boxes[best].detach().clone()
        del results, scores, masks, boxes, keep, keep_scores, keep_indices, frame, image_in, text_embeddings, text_mask
        mask = _refine_detector_mask(
            sam3_model,
            image[0],
            coarse_mask,
            box_xyxy,
            height,
            width,
            device,
            dtype,
        )
        mask = (mask > 0).float()
        return _soften_alpha(mask, blur_radius=2)


def _fallback_person_alpha(image):
    frame = image[0, ..., :3]
    height, width, _ = frame.shape
    border = max(2, min(height, width) // 80)
    samples = torch.cat(
        [
            frame[:border].reshape(-1, 3),
            frame[-border:].reshape(-1, 3),
            frame[:, :border].reshape(-1, 3),
            frame[:, -border:].reshape(-1, 3),
        ],
        dim=0,
    )
    bg = samples.median(dim=0).values
    dist = (frame - bg).abs().mean(dim=-1)
    alpha = (dist > 0.055).float()
    alpha = F.max_pool2d(alpha.unsqueeze(0).unsqueeze(0), kernel_size=7, stride=1, padding=3)[0, 0]
    return _soften_alpha(alpha, blur_radius=2)


def _prepare_cutout(image, alpha):
    frame = image[0, ..., :3]
    height, width = alpha.shape
    bbox = _mask_bbox(alpha, pad=max(8, min(height, width) // 80))
    if bbox is None:
        alpha = _fallback_person_alpha(image).to(frame.device)
        bbox = _mask_bbox(alpha, pad=max(8, min(height, width) // 80))
    if bbox is None:
        bbox = (0, 0, width, height)
        alpha = torch.ones((height, width), device=frame.device, dtype=frame.dtype)
    x1, y1, x2, y2 = bbox
    return {
        "rgb": frame[y1:y2, x1:x2].contiguous(),
        "alpha": alpha[y1:y2, x1:x2].contiguous(),
        "width": x2 - x1,
        "height": y2 - y1,
    }


def _aspect_mode(width, height):
    ratio = width / max(1, height)
    if ratio < 0.88:
        return "portrait"
    if ratio > 1.12:
        return "landscape"
    return "square"


def _aspect_band(width, height):
    ratio = width / max(1, height)
    if ratio <= 0.52:
        return "portrait_ultra"  # 1:2, 9:19.5, similarly narrow tall canvases.
    if ratio <= 0.68:
        return "portrait_tall"  # 9:16, 2:3.
    if ratio < 0.88:
        return "portrait_medium"  # 3:4, 4:5.
    if ratio <= 1.12:
        return "square"
    if ratio <= 1.48:
        return "landscape_medium"  # 4:3.
    if ratio <= 1.90:
        return "landscape_wide"  # 3:2, 16:9.
    return "landscape_ultra"  # 2:1, 21:9 and wider.


def _layout_ratio_key(width, height):
    ratio = width / max(1, height)
    ratio_map = {
        "1_2": 1.0 / 2.0,
        "9_16": 9.0 / 16.0,
        "2_3": 2.0 / 3.0,
        "3_4": 3.0 / 4.0,
        "1_1": 1.0,
        "4_3": 4.0 / 3.0,
        "3_2": 3.0 / 2.0,
        "16_9": 16.0 / 9.0,
        "2_1": 2.0,
    }
    return min(ratio_map, key=lambda key: abs(ratio - ratio_map[key]))


def _layout_spec(x, base, max_h, max_w, z):
    return {"x": x, "base": base, "max_h": max_h, "max_w": max_w, "z": z}


def _evenly_spaced(start, end, count):
    if count <= 1:
        return [0.5]
    step = (end - start) / (count - 1)
    return [start + step * i for i in range(count)]


def _row_specs(count, start, end, max_h, max_w, base=0.99):
    return [_layout_spec(x, base, max_h, max_w, i) for i, x in enumerate(_evenly_spaced(start, end, count))]


def _scale_spec_widths(specs, factor):
    if factor == 1.0:
        return specs
    return [
        {
            **spec,
            "max_w": spec["max_w"] * factor,
        }
        for spec in specs
    ]


def _make_layout(specs):
    return [
        _layout_spec(
            item["x"],
            item.get("base", 0.99),
            item["max_h"],
            item["max_w"],
            item.get("z", index),
        )
        for index, item in enumerate(specs)
    ]


def _layout_specs(count, width, height):
    mode = _aspect_mode(width, height)
    band = _aspect_band(width, height)
    ratio_key = _layout_ratio_key(width, height)

    if count <= 0:
        return mode, []

    if count == 1:
        if band in ("landscape_wide", "landscape_ultra"):
            return mode, _make_layout([{"x": 0.5, "max_h": 0.98, "max_w": 0.19}])
        if band == "landscape_medium":
            return mode, _make_layout([{"x": 0.5, "max_h": 0.98, "max_w": 0.25}])
        if band == "square":
            return mode, _make_layout([{"x": 0.5, "max_h": 0.98, "max_w": 0.33}])
        if band == "portrait_medium":
            return mode, _make_layout([{"x": 0.5, "max_h": 0.98, "max_w": 0.40}])
        return mode, _make_layout([{"x": 0.5, "max_h": 0.98, "max_w": 0.46}])

    exact_ratio_templates = {
        "1_2": {
            2: [
                {"x": 0.255, "base": 0.905, "max_h": 0.845, "max_w": 0.49},
                {"x": 0.745, "base": 0.905, "max_h": 0.845, "max_w": 0.49},
            ],
            3: [
                {"x": 0.21, "base": 0.99, "max_h": 0.62, "max_w": 0.31, "z": 1},
                {"x": 0.50, "base": 0.59, "max_h": 0.59, "max_w": 0.34, "z": 0},
                {"x": 0.79, "base": 0.99, "max_h": 0.62, "max_w": 0.31, "z": 2},
            ],
            4: [
                {"x": 0.18, "base": 0.99, "max_h": 0.58, "max_w": 0.27, "z": 2},
                {"x": 0.40, "base": 0.60, "max_h": 0.58, "max_w": 0.31, "z": 0},
                {"x": 0.58, "base": 0.99, "max_h": 0.58, "max_w": 0.27, "z": 3},
                {"x": 0.82, "base": 0.60, "max_h": 0.58, "max_w": 0.31, "z": 1},
            ],
            5: [
                {"x": 0.16, "base": 0.99, "max_h": 0.57, "max_w": 0.24, "z": 2},
                {"x": 0.34, "base": 0.60, "max_h": 0.58, "max_w": 0.28, "z": 0},
                {"x": 0.50, "base": 0.99, "max_h": 0.57, "max_w": 0.24, "z": 3},
                {"x": 0.66, "base": 0.60, "max_h": 0.58, "max_w": 0.28, "z": 1},
                {"x": 0.84, "base": 0.99, "max_h": 0.57, "max_w": 0.24, "z": 4},
            ],
        },
        "9_16": {
            2: [
                {"x": 0.255, "base": 0.985, "max_h": 0.934, "max_w": 0.49},
                {"x": 0.745, "base": 0.985, "max_h": 0.934, "max_w": 0.49},
            ],
            3: [
                {"x": 0.22, "base": 0.99, "max_h": 0.64, "max_w": 0.33, "z": 1},
                {"x": 0.50, "base": 0.60, "max_h": 0.60, "max_w": 0.37, "z": 0},
                {"x": 0.78, "base": 0.99, "max_h": 0.64, "max_w": 0.33, "z": 2},
            ],
            4: [
                {"x": 0.16, "base": 0.99, "max_h": 0.61, "max_w": 0.30, "z": 2},
                {"x": 0.39, "base": 0.62, "max_h": 0.61, "max_w": 0.34, "z": 0},
                {"x": 0.61, "base": 0.99, "max_h": 0.61, "max_w": 0.30, "z": 3},
                {"x": 0.84, "base": 0.62, "max_h": 0.61, "max_w": 0.34, "z": 1},
            ],
            5: [
                {"x": 0.15, "base": 0.99, "max_h": 0.61, "max_w": 0.27, "z": 2},
                {"x": 0.37, "base": 0.62, "max_h": 0.61, "max_w": 0.32, "z": 0},
                {"x": 0.50, "base": 0.99, "max_h": 0.61, "max_w": 0.27, "z": 3},
                {"x": 0.73, "base": 0.62, "max_h": 0.61, "max_w": 0.32, "z": 1},
                {"x": 0.85, "base": 0.99, "max_h": 0.61, "max_w": 0.27, "z": 4},
            ],
        },
        "2_3": {
            2: [
                {"x": 0.255, "base": 0.988, "max_h": 0.98, "max_w": 0.43},
                {"x": 0.745, "base": 0.988, "max_h": 0.98, "max_w": 0.43},
            ],
            3: [
                {"x": 0.20, "base": 0.99, "max_h": 0.67, "max_w": 0.31, "z": 1},
                {"x": 0.50, "base": 0.70, "max_h": 0.70, "max_w": 0.36, "z": 0},
                {"x": 0.80, "base": 0.99, "max_h": 0.67, "max_w": 0.31, "z": 2},
            ],
            4: [
                {"x": 0.15, "base": 0.99, "max_h": 0.65, "max_w": 0.28, "z": 2},
                {"x": 0.39, "base": 0.66, "max_h": 0.66, "max_w": 0.33, "z": 0},
                {"x": 0.61, "base": 0.99, "max_h": 0.65, "max_w": 0.28, "z": 3},
                {"x": 0.85, "base": 0.66, "max_h": 0.66, "max_w": 0.33, "z": 1},
            ],
            5: [
                {"x": 0.16, "base": 0.99, "max_h": 0.70, "max_w": 0.27, "z": 2},
                {"x": 0.34, "base": 0.67, "max_h": 0.67, "max_w": 0.33, "z": 0},
                {"x": 0.50, "base": 0.99, "max_h": 0.70, "max_w": 0.27, "z": 3},
                {"x": 0.66, "base": 0.67, "max_h": 0.67, "max_w": 0.33, "z": 1},
                {"x": 0.84, "base": 0.99, "max_h": 0.70, "max_w": 0.27, "z": 4},
            ],
        },
        "4_3": {
            3: [
                {"x": 0.20, "base": 0.99, "max_h": 0.82, "max_w": 0.35, "z": 1},
                {"x": 0.50, "base": 0.82, "max_h": 0.82, "max_w": 0.39, "z": 0},
                {"x": 0.80, "base": 0.99, "max_h": 0.82, "max_w": 0.35, "z": 2},
            ],
            4: [
                {"x": 0.16, "base": 0.99, "max_h": 0.71, "max_w": 0.31, "z": 2},
                {"x": 0.39, "base": 0.78, "max_h": 0.78, "max_w": 0.34, "z": 0},
                {"x": 0.56, "base": 0.99, "max_h": 0.71, "max_w": 0.31, "z": 3},
                {"x": 0.80, "base": 0.78, "max_h": 0.78, "max_w": 0.34, "z": 1},
            ],
            5: [
                {"x": 0.14, "base": 0.99, "max_h": 0.69, "max_w": 0.28, "z": 2},
                {"x": 0.37, "base": 0.78, "max_h": 0.78, "max_w": 0.32, "z": 0},
                {"x": 0.50, "base": 0.99, "max_h": 0.69, "max_w": 0.28, "z": 3},
                {"x": 0.73, "base": 0.78, "max_h": 0.78, "max_w": 0.32, "z": 1},
                {"x": 0.86, "base": 0.99, "max_h": 0.69, "max_w": 0.28, "z": 4},
            ],
        },
        "1_1": {
            4: [
                {"x": 0.15, "base": 0.915, "max_h": 0.83, "max_w": 0.28},
                {"x": 0.38, "base": 0.915, "max_h": 0.83, "max_w": 0.28},
                {"x": 0.62, "base": 0.915, "max_h": 0.83, "max_w": 0.28},
                {"x": 0.85, "base": 0.915, "max_h": 0.83, "max_w": 0.28},
            ],
            5: [
                {"x": 0.14, "base": 0.857, "max_h": 0.69, "max_w": 0.22},
                {"x": 0.32, "base": 0.857, "max_h": 0.69, "max_w": 0.22},
                {"x": 0.50, "base": 0.857, "max_h": 0.69, "max_w": 0.22},
                {"x": 0.68, "base": 0.857, "max_h": 0.69, "max_w": 0.22},
                {"x": 0.86, "base": 0.857, "max_h": 0.69, "max_w": 0.22},
            ],
        },
    }
    if ratio_key in exact_ratio_templates and count in exact_ratio_templates[ratio_key]:
        return mode, _make_layout(exact_ratio_templates[ratio_key][count])

    landscape_templates = {
        2: {
            "landscape_medium": [{"x": 0.31, "max_h": 0.98, "max_w": 0.22}, {"x": 0.69, "max_h": 0.98, "max_w": 0.22}],
            "landscape_wide": [{"x": 0.35, "max_h": 0.98, "max_w": 0.16}, {"x": 0.65, "max_h": 0.98, "max_w": 0.16}],
            "landscape_ultra": [{"x": 0.35, "max_h": 0.98, "max_w": 0.145}, {"x": 0.65, "max_h": 0.98, "max_w": 0.145}],
        },
        3: {
            "landscape_medium": [{"x": 0.22, "max_h": 0.98, "max_w": 0.22}, {"x": 0.50, "max_h": 0.98, "max_w": 0.22}, {"x": 0.78, "max_h": 0.98, "max_w": 0.22}],
            "landscape_wide": [{"x": 0.21, "max_h": 0.98, "max_w": 0.16}, {"x": 0.50, "max_h": 0.98, "max_w": 0.16}, {"x": 0.79, "max_h": 0.98, "max_w": 0.16}],
            "landscape_ultra": [{"x": 0.27, "max_h": 0.98, "max_w": 0.145}, {"x": 0.50, "max_h": 0.98, "max_w": 0.145}, {"x": 0.73, "max_h": 0.98, "max_w": 0.145}],
        },
        4: {
            "landscape_medium": [{"x": 0.13, "max_h": 0.98, "max_w": 0.22}, {"x": 0.38, "max_h": 0.98, "max_w": 0.22}, {"x": 0.62, "max_h": 0.98, "max_w": 0.22}, {"x": 0.87, "max_h": 0.98, "max_w": 0.22}],
            "landscape_wide": [{"x": 0.14, "max_h": 0.98, "max_w": 0.16}, {"x": 0.38, "max_h": 0.98, "max_w": 0.16}, {"x": 0.62, "max_h": 0.98, "max_w": 0.16}, {"x": 0.86, "max_h": 0.98, "max_w": 0.16}],
            "landscape_ultra": [{"x": 0.15, "max_h": 0.98, "max_w": 0.145}, {"x": 0.38, "max_h": 0.98, "max_w": 0.145}, {"x": 0.62, "max_h": 0.98, "max_w": 0.145}, {"x": 0.85, "max_h": 0.98, "max_w": 0.145}],
        },
        5: {
            "landscape_medium": [{"x": 0.11, "max_h": 0.98, "max_w": 0.22}, {"x": 0.31, "max_h": 0.98, "max_w": 0.22}, {"x": 0.50, "max_h": 0.98, "max_w": 0.22}, {"x": 0.69, "max_h": 0.98, "max_w": 0.22}, {"x": 0.89, "max_h": 0.98, "max_w": 0.22}],
            "landscape_wide": [{"x": 0.14, "max_h": 0.98, "max_w": 0.16}, {"x": 0.32, "max_h": 0.98, "max_w": 0.16}, {"x": 0.50, "max_h": 0.98, "max_w": 0.16}, {"x": 0.68, "max_h": 0.98, "max_w": 0.16}, {"x": 0.86, "max_h": 0.98, "max_w": 0.16}],
            "landscape_ultra": [{"x": 0.12, "max_h": 0.98, "max_w": 0.145}, {"x": 0.31, "max_h": 0.98, "max_w": 0.145}, {"x": 0.50, "max_h": 0.98, "max_w": 0.145}, {"x": 0.69, "max_h": 0.98, "max_w": 0.145}, {"x": 0.88, "max_h": 0.98, "max_w": 0.145}],
        },
    }

    square_templates = {
        2: [{"x": 0.31, "max_h": 0.98, "max_w": 0.29}, {"x": 0.69, "max_h": 0.98, "max_w": 0.29}],
        3: [{"x": 0.19, "max_h": 0.98, "max_w": 0.29}, {"x": 0.50, "max_h": 0.98, "max_w": 0.29}, {"x": 0.81, "max_h": 0.98, "max_w": 0.29}],
        4: [{"x": 0.145, "base": 0.915, "max_h": 0.83, "max_w": 0.24}, {"x": 0.382, "base": 0.915, "max_h": 0.83, "max_w": 0.24}, {"x": 0.618, "base": 0.915, "max_h": 0.83, "max_w": 0.24}, {"x": 0.855, "base": 0.915, "max_h": 0.83, "max_w": 0.24}],
        5: [{"x": 0.14, "base": 0.857, "max_h": 0.69, "max_w": 0.19}, {"x": 0.32, "base": 0.857, "max_h": 0.69, "max_w": 0.19}, {"x": 0.50, "base": 0.857, "max_h": 0.69, "max_w": 0.19}, {"x": 0.68, "base": 0.857, "max_h": 0.69, "max_w": 0.19}, {"x": 0.86, "base": 0.857, "max_h": 0.69, "max_w": 0.19}],
    }

    portrait_medium_templates = {
        2: [{"x": 0.255, "max_h": 0.98, "max_w": 0.43}, {"x": 0.745, "max_h": 0.98, "max_w": 0.43}],
        3: [{"x": 0.19, "max_h": 0.98, "max_w": 0.39}, {"x": 0.50, "max_h": 0.98, "max_w": 0.39}, {"x": 0.81, "max_h": 0.98, "max_w": 0.39}],
        4: [{"x": 0.145, "max_h": 0.98, "max_w": 0.29}, {"x": 0.38, "max_h": 0.98, "max_w": 0.29}, {"x": 0.62, "max_h": 0.98, "max_w": 0.29}, {"x": 0.855, "max_h": 0.98, "max_w": 0.29}],
        5: [{"x": 0.11, "max_h": 0.98, "max_w": 0.29}, {"x": 0.305, "max_h": 0.98, "max_w": 0.29}, {"x": 0.50, "max_h": 0.98, "max_w": 0.29}, {"x": 0.695, "max_h": 0.98, "max_w": 0.29}, {"x": 0.89, "max_h": 0.98, "max_w": 0.29}],
    }

    portrait_tall_templates = {
        2: [{"x": 0.255, "max_h": 0.98, "max_w": 0.43}, {"x": 0.745, "max_h": 0.98, "max_w": 0.43}],
        3: [
            {"x": 0.21, "max_h": 0.82, "max_w": 0.36, "z": 1},
            {"x": 0.50, "max_h": 0.98, "max_w": 0.44, "base": 0.86, "z": 0},
            {"x": 0.79, "max_h": 0.82, "max_w": 0.36, "z": 2},
        ],
        4: [
            {"x": 0.145, "max_h": 0.65, "max_w": 0.29, "z": 2},
            {"x": 0.38, "max_h": 0.65, "max_w": 0.29, "base": 0.66, "z": 0},
            {"x": 0.62, "max_h": 0.65, "max_w": 0.29, "z": 3},
            {"x": 0.855, "max_h": 0.65, "max_w": 0.29, "base": 0.66, "z": 1},
        ],
        5: [
            {"x": 0.16, "max_h": 0.70, "max_w": 0.29, "z": 2},
            {"x": 0.33, "max_h": 0.98, "max_w": 0.36, "base": 0.86, "z": 0},
            {"x": 0.50, "max_h": 0.70, "max_w": 0.29, "z": 3},
            {"x": 0.67, "max_h": 0.98, "max_w": 0.36, "base": 0.86, "z": 1},
            {"x": 0.84, "max_h": 0.70, "max_w": 0.29, "z": 4},
        ],
    }

    portrait_ultra_templates = {
        2: [{"x": 0.255, "max_h": 0.85, "max_w": 0.49}, {"x": 0.745, "max_h": 0.85, "max_w": 0.49}],
        3: [
            {"x": 0.21, "max_h": 0.58, "max_w": 0.36, "z": 1},
            {"x": 0.50, "max_h": 0.85, "max_w": 0.49, "base": 0.72, "z": 0},
            {"x": 0.79, "max_h": 0.58, "max_w": 0.36, "z": 2},
        ],
        4: [
            {"x": 0.275, "max_h": 0.98, "max_w": 0.55, "z": 1},
            {"x": 0.705, "max_h": 0.98, "max_w": 0.58, "z": 0},
        ],
        5: [
            {"x": 0.255, "max_h": 0.98, "max_w": 0.50, "z": 1},
            {"x": 0.745, "max_h": 0.98, "max_w": 0.50, "z": 0},
        ],
    }

    if band in ("landscape_medium", "landscape_wide", "landscape_ultra"):
        return mode, _make_layout(landscape_templates[min(count, 5)][band])
    if band == "square":
        return mode, _make_layout(square_templates[min(count, 5)])
    if band == "portrait_medium":
        return mode, _make_layout(portrait_medium_templates[min(count, 5)])
    if band == "portrait_tall":
        return mode, _make_layout(portrait_tall_templates[min(count, 5)])
    return mode, _make_layout(portrait_ultra_templates[min(count, 5)])


def _paste_cutout(canvas, canvas_alpha, cutout, spec, out_width, out_height):
    rgb = cutout["rgb"].movedim(-1, 0).unsqueeze(0)
    alpha = cutout["alpha"].unsqueeze(0).unsqueeze(0)
    target_h = max(1, int(out_height * spec["max_h"]))
    target_w = max(1, int(out_width * spec["max_w"]))
    scale = min(target_w / max(1, cutout["width"]), target_h / max(1, cutout["height"]))
    new_w = max(1, int(round(cutout["width"] * scale)))
    new_h = max(1, int(round(cutout["height"] * scale)))

    rgb = F.interpolate(rgb, size=(new_h, new_w), mode="bilinear", align_corners=False)[0].movedim(0, -1)
    alpha = F.interpolate(alpha, size=(new_h, new_w), mode="bilinear", align_corners=False)[0, 0].clamp(0, 1)

    cx = int(round(out_width * spec["x"]))
    baseline = int(round(out_height * spec["base"]))
    x0 = cx - new_w // 2
    y0 = baseline - new_h
    x1 = x0 + new_w
    y1 = y0 + new_h
    src_x0 = max(0, -x0)
    src_y0 = max(0, -y0)
    dst_x0 = max(0, x0)
    dst_y0 = max(0, y0)
    dst_x1 = min(out_width, x1)
    dst_y1 = min(out_height, y1)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return
    src_x1 = src_x0 + (dst_x1 - dst_x0)
    src_y1 = src_y0 + (dst_y1 - dst_y0)
    src_rgb = rgb[src_y0:src_y1, src_x0:src_x1]
    src_alpha = alpha[src_y0:src_y1, src_x0:src_x1].unsqueeze(-1)
    dst = canvas[dst_y0:dst_y1, dst_x0:dst_x1]
    canvas[dst_y0:dst_y1, dst_x0:dst_x1] = src_rgb * src_alpha + dst * (1.0 - src_alpha)
    old_alpha = canvas_alpha[dst_y0:dst_y1, dst_x0:dst_x1]
    canvas_alpha[dst_y0:dst_y1, dst_x0:dst_x1] = torch.maximum(old_alpha, src_alpha[..., 0])


def _compose_collage(cutouts, width, height, background):
    device = comfy.model_management.intermediate_device()
    dtype = torch.float32
    bg = torch.tensor(_background_rgb(background), device=device, dtype=dtype)
    canvas = bg.view(1, 1, 3).expand(height, width, 3).clone()
    canvas_alpha = torch.zeros((height, width), device=device, dtype=dtype)
    _, specs = _layout_specs(len(cutouts), width, height)
    draw_items = []
    for index, (cutout, spec) in enumerate(zip(cutouts, specs)):
        local = {
            "rgb": cutout["rgb"].to(device=device, dtype=dtype),
            "alpha": cutout["alpha"].to(device=device, dtype=dtype),
            "width": cutout["width"],
            "height": cutout["height"],
        }
        draw_items.append((spec.get("z", index), index, local, spec))
    for _, _, local, spec in sorted(draw_items):
        _paste_cutout(canvas, canvas_alpha, local, spec, width, height)
    return canvas.unsqueeze(0).clamp(0, 1), canvas_alpha.unsqueeze(0).clamp(0, 1)


def _default_manual_layout(count, width, height):
    if count <= 0:
        return []
    min_scale = min(width / max(1, height), height / max(1, width))
    scale = max(0.2, min(0.55, 0.38 * min_scale + 0.14))
    return [
        {
            "x": (index + 0.5) / count,
            "y": 0.72,
            "scale": scale,
            "z": count - index,
        }
        for index in range(count)
    ]


def _parse_manual_layout(layout_json, count, width, height, background, use_layout_size=True):
    layout = {}
    if isinstance(layout_json, str) and layout_json.strip():
        try:
            decoded = json.loads(layout_json)
            if isinstance(decoded, dict):
                layout = decoded
        except json.JSONDecodeError:
            LOGGER.warning("ManualRefCollage: invalid layout_json; using default layout.")

    output_width = _clamp_manual_dimension(layout.get("width") if use_layout_size else width, width)
    output_height = _clamp_manual_dimension(layout.get("height") if use_layout_size else height, height)

    output_background = str(layout.get("background") or background or "black").lower()
    if output_background not in ("white", "black"):
        output_background = "black"

    raw_items = layout.get("items")
    default_items = _default_manual_layout(count, output_width, output_height)
    items = []
    for index in range(count):
        item = raw_items[index] if isinstance(raw_items, list) and index < len(raw_items) and isinstance(raw_items[index], dict) else {}
        fallback = default_items[index]
        try:
            x = float(item.get("x", fallback["x"]))
            y = float(item.get("y", fallback["y"]))
            scale = float(item.get("scale", fallback["scale"]))
            z = int(item.get("z", fallback["z"]))
        except (TypeError, ValueError):
            x, y, scale, z = fallback["x"], fallback["y"], fallback["scale"], fallback["z"]
        items.append(
            {
                "x": max(-1.0, min(2.0, x)),
                "y": max(-1.0, min(2.0, y)),
                "scale": max(0.02, min(4.0, scale)),
                "z": z,
            }
        )
    return output_width, output_height, output_background, items


def _paste_manual_cutout(canvas, canvas_alpha, cutout, item, out_width, out_height):
    rgb = cutout["rgb"].to(device=canvas.device, dtype=canvas.dtype).movedim(-1, 0).unsqueeze(0)
    alpha = cutout["alpha"].to(device=canvas.device, dtype=canvas.dtype).unsqueeze(0).unsqueeze(0)
    base = min(out_width, out_height)
    target_h = max(1, int(round(base * item["scale"])))
    scale = target_h / max(1, cutout["height"])
    new_w = max(1, int(round(cutout["width"] * scale)))
    new_h = max(1, int(round(cutout["height"] * scale)))

    rgb = F.interpolate(rgb, size=(new_h, new_w), mode="bilinear", align_corners=False)[0].movedim(0, -1)
    alpha = F.interpolate(alpha, size=(new_h, new_w), mode="bilinear", align_corners=False)[0, 0].clamp(0, 1)

    cx = int(round(item["x"] * out_width))
    cy = int(round(item["y"] * out_height))
    x0 = cx - new_w // 2
    y0 = cy - new_h // 2
    x1 = x0 + new_w
    y1 = y0 + new_h

    src_x0 = max(0, -x0)
    src_y0 = max(0, -y0)
    dst_x0 = max(0, x0)
    dst_y0 = max(0, y0)
    dst_x1 = min(out_width, x1)
    dst_y1 = min(out_height, y1)
    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return

    src_x1 = src_x0 + (dst_x1 - dst_x0)
    src_y1 = src_y0 + (dst_y1 - dst_y0)
    src_rgb = rgb[src_y0:src_y1, src_x0:src_x1]
    src_alpha = alpha[src_y0:src_y1, src_x0:src_x1].unsqueeze(-1)
    dst = canvas[dst_y0:dst_y1, dst_x0:dst_x1]
    canvas[dst_y0:dst_y1, dst_x0:dst_x1] = src_rgb * src_alpha + dst * (1.0 - src_alpha)
    old_alpha = canvas_alpha[dst_y0:dst_y1, dst_x0:dst_x1]
    canvas_alpha[dst_y0:dst_y1, dst_x0:dst_x1] = torch.maximum(old_alpha, src_alpha[..., 0])


def _build_manual_background_canvas(out_width, out_height, background, background_frame=None, background_opacity=0.0):
    device = comfy.model_management.intermediate_device()
    dtype = torch.float32
    bg = torch.tensor(_background_rgb(background), device=device, dtype=dtype)
    canvas = bg.view(1, 1, 3).expand(out_height, out_width, 3).clone()
    opacity = max(0.0, min(float(background_opacity), 1.0))
    if background_frame is None or opacity <= 0.0:
        return canvas

    rgb = background_frame[:1, ..., :3].to(device=device, dtype=dtype).movedim(-1, 1)
    rgb = F.interpolate(rgb, size=(out_height, out_width), mode="bilinear", align_corners=False)[0].movedim(0, -1)
    return rgb.clamp(0, 1) * opacity + canvas * (1.0 - opacity)


def _compose_manual_collage(
    cutouts,
    width,
    height,
    background,
    layout_json,
    background_frame=None,
    background_opacity=0.0,
    use_layout_size=True,
):
    out_width, out_height, out_background, items = _parse_manual_layout(
        layout_json,
        len(cutouts),
        int(width),
        int(height),
        background,
        use_layout_size=use_layout_size,
    )
    device = comfy.model_management.intermediate_device()
    dtype = torch.float32
    canvas = _build_manual_background_canvas(
        out_width,
        out_height,
        out_background,
        background_frame=background_frame,
        background_opacity=background_opacity,
    ).to(device=device, dtype=dtype)
    canvas_alpha = torch.zeros((out_height, out_width), device=device, dtype=dtype)
    draw_items = []
    for index, item in enumerate(items):
        cutout = cutouts[index] if index < len(cutouts) else None
        if cutout is None:
            continue
        draw_items.append((item["z"], index, cutout, item))
    for _, index, cutout, item in sorted(draw_items):
        _paste_manual_cutout(canvas, canvas_alpha, cutout, item, out_width, out_height)
    return canvas.unsqueeze(0).clamp(0, 1), canvas_alpha.unsqueeze(0).clamp(0, 1)


def _blank_collage_output(width, height, background):
    collage = _blank_images(1, height, width, background)
    alpha_mask = torch.zeros((1, height, width), device=collage.device, dtype=collage.dtype)
    return collage, alpha_mask

def _unpack(track_data):
    packed = track_data["packed_masks"]
    if packed is None or packed.shape[1] == 0:
        return None
    return unpack_masks(packed)


def _first_frame_cx_area(masks_bool):
    first = masks_bool[0].float()
    height, width = first.shape[-2], first.shape[-1]
    n_pixels = height * width
    grid_x = torch.arange(width, device=first.device, dtype=first.dtype).view(1, width)
    area = first.sum(dim=(-1, -2)).clamp_(min=1)
    cx = (first * grid_x).sum(dim=(-1, -2)) / area
    return (cx / width).tolist(), (area / n_pixels).tolist()


def _subset_track_data(track_data, obj_indices):
    out = dict(track_data)
    packed = track_data["packed_masks"]
    if packed is None or not obj_indices:
        out["packed_masks"] = None
        if "scores" in out:
            out["scores"] = []
        return out
    out["packed_masks"] = packed[:, obj_indices].contiguous()
    scores = track_data.get("scores")
    if scores is not None:
        out["scores"] = [scores[i] for i in obj_indices if i < len(scores)]
    return out


def _background_rgb(background):
    return (1.0, 1.0, 1.0) if background.startswith("white") else (0.0, 0.0, 0.0)


def _render_device(render_device="auto"):
    if render_device == "cpu":
        return torch.device("cpu")
    if render_device in ("auto", "gpu"):
        return comfy.model_management.get_torch_device()
    return comfy.model_management.intermediate_device()


def _render_dtype(device):
    dtype = comfy.model_management.intermediate_dtype()
    if device.type == "cpu" and dtype == torch.float16:
        return torch.float32
    return dtype


def _has_any_mask(packed, device):
    if packed is None or packed.shape[1] == 0:
        return False
    return bool(unpack_masks(packed.to(device)).any().item())


def _blank_images(frame_count, height, width, background, render_device="auto"):
    device = _render_device(render_device)
    dtype = _render_dtype(device)
    bg_rgb = _background_rgb(background)
    out = torch.empty(frame_count, height, width, 3, device=device, dtype=dtype)
    out[..., 0], out[..., 1], out[..., 2] = bg_rgb[0], bg_rgb[1], bg_rgb[2]
    return out


def _render_colored_masks(track_data, background="black", render_device="auto"):
    packed = track_data["packed_masks"]
    height, width = track_data["orig_size"]
    device = _render_device(render_device)
    dtype = _render_dtype(device)
    bg_rgb = _background_rgb(background)
    if packed is None or packed.shape[1] == 0:
        frame_count = track_data.get("n_frames", 1) if packed is None else packed.shape[0]
        return _blank_images(max(1, frame_count), height, width, background, render_device)

    frame_count, n_obj = packed.shape[0], packed.shape[1]
    colors = torch.tensor(
        [DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)] for i in range(n_obj)],
        device=device,
        dtype=dtype,
    )
    masks_full = unpack_masks(packed.to(device)).float()
    mask_height, mask_width = masks_full.shape[-2], masks_full.shape[-1]
    masks_full = F.interpolate(
        masks_full.view(frame_count * n_obj, 1, mask_height, mask_width),
        size=(height, width),
        mode="nearest",
    ).view(frame_count, n_obj, height, width) > 0.5
    any_mask = masks_full.any(dim=1)
    obj_idx_map = masks_full.to(torch.uint8).argmax(dim=1)
    color_overlay = colors[obj_idx_map]
    bg_tensor = torch.tensor(bg_rgb, device=device, dtype=color_overlay.dtype).view(1, 1, 1, 3)
    return torch.where(any_mask.unsqueeze(-1), color_overlay, bg_tensor.expand_as(color_overlay))


def _render_prefix_image_masks(
    track_data,
    background="white",
    prefix_mask_mode="Multi Image Single Color",
    max_images=5,
    render_device="auto",
):
    packed = track_data["packed_masks"]
    height, width = track_data["orig_size"]

    if packed is None or packed.shape[1] == 0:
        frame_count = track_data.get("n_frames", 1) if packed is None else packed.shape[0]
        LOGGER.warning("SCAIL2ColoredMaskV2: prefix_track_data has no objects; prefix_image_mask is blank.")
        return _blank_images(max(1, min(frame_count, max_images)), height, width, background, render_device)

    frame_count = max(1, min(packed.shape[0], max_images))
    packed = packed[:frame_count]
    n_obj = packed.shape[1]
    if n_obj == 0:
        LOGGER.warning("SCAIL2ColoredMaskV2: prefix_track_data has zero objects; prefix_image_mask is blank.")
        return _blank_images(frame_count, height, width, background, render_device)

    device = _render_device(render_device)
    dtype = _render_dtype(device)
    masks_full = unpack_masks(packed.to(device)).float()
    if not masks_full.any():
        LOGGER.warning("SCAIL2ColoredMaskV2: prefix_track_data masks are empty; prefix_image_mask is blank.")
    mask_height, mask_width = masks_full.shape[-2], masks_full.shape[-1]
    masks_full = F.interpolate(
        masks_full.view(frame_count * n_obj, 1, mask_height, mask_width),
        size=(height, width),
        mode="nearest",
    ).view(frame_count, n_obj, height, width) > 0.5

    bg = torch.tensor(_background_rgb(background), device=device, dtype=dtype).view(1, 1, 1, 3)
    blank = bg.expand(frame_count, height, width, 3)
    any_mask = masks_full.any(dim=1)

    if prefix_mask_mode == "Multi Image Single Color":
        color = torch.tensor(DEFAULT_PALETTE[0], device=device, dtype=dtype).view(1, 1, 1, 3)
        color_overlay = color.expand(frame_count, height, width, 3)
        return torch.where(any_mask.unsqueeze(-1), color_overlay, blank)

    if prefix_mask_mode == "Single Image Multi Color":
        colors = torch.tensor(
            [PREFIX_BATCH_PALETTE[i % len(PREFIX_BATCH_PALETTE)] for i in range(frame_count)],
            device=device,
            dtype=dtype,
        ).view(frame_count, 1, 1, 3)
        color_overlay = colors.expand(frame_count, height, width, 3)
        return torch.where(any_mask.unsqueeze(-1), color_overlay, blank)

    colors = torch.tensor(
        [DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)] for i in range(n_obj)],
        device=device,
        dtype=dtype,
    )
    obj_idx_map = masks_full.to(torch.uint8).argmax(dim=1)
    color_overlay = colors[obj_idx_map]
    return torch.where(any_mask.unsqueeze(-1), color_overlay, blank)


class SCAIL2ColoredMaskV2(io.ComfyNode):
    """Render SCAIL-2 colored masks plus a prefix-image colored batch mask."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SCAIL2ColoredMaskV2",
            display_name="Create SCAIL-2 Colored Mask V2",
            category="conditioning/video_models/scail",
            inputs=[
                SAM3TrackData.Input(
                    "driving_track_data",
                    tooltip="SAM3 track of the driving pose video. Will be rendered into the pose_video_mask output.",
                ),
                SAM3TrackData.Input(
                    "ref_track_data",
                    optional=True,
                    tooltip="SAM3 track of the reference image.",
                ),
                SAM3TrackData.Input(
                    "prefix_track_data",
                    optional=True,
                    tooltip="SAM3 track of a prefix image batch. The first 5 frames are rendered into prefix_image_mask.",
                ),
                io.String.Input(
                    "object_indices",
                    default="",
                    tooltip="Comma-separated list of person indices to include (e.g. '0,2,3'). Applied to driving, reference, and prefix masks. Empty = all.",
                ),
                io.Combo.Input(
                    "sort_by",
                    options=["none", "left_to_right", "area"],
                    default="left_to_right",
                    tooltip="Order in which palette colors are assigned to tracked objects. left_to_right = leftmost object gets the first color; area = biggest object gets the first color; none = keep SAM3's order.",
                ),
                io.Combo.Input(
                    "prefix_mask_mode",
                    options=["Multi Image Single Color", "Multi Image Multi Color", "Single Image Multi Color"],
                    default="Multi Image Single Color",
                    tooltip="Multi Image Single Color = each output batch image is single-color matching the reference_image_mask foreground color. Multi Image Multi Color = each batch image uses object colors by the node palette rule. Single Image Multi Color = single-color output by batch order: blue, red, green, magenta, cyan, then loop.",
                ),
                io.Boolean.Input(
                    "replacement_mode",
                    default=False,
                    tooltip="False = Animation Mode (pose_video_mask black background, reference_image_mask and prefix_image_mask white background). True = Replacement Mode (pose_video_mask white background, reference_image_mask and prefix_image_mask black background).",
                ),
                io.Combo.Input(
                    "render_device",
                    options=["auto", "gpu", "cpu"],
                    default="auto",
                    tooltip="Device used to render the RGB mask tensors. auto/gpu uses ComfyUI's current torch device; cpu uses system memory.",
                ),
            ],
            outputs=[
                io.Image.Output("pose_video_mask"),
                io.Image.Output("reference_image_mask"),
                io.Image.Output("prefix_image_mask"),
            ],
            is_experimental=True,
        )

    @classmethod
    def execute(
        cls,
        driving_track_data,
        object_indices,
        sort_by,
        prefix_mask_mode,
        replacement_mode,
        render_device="auto",
        ref_track_data=None,
        prefix_track_data=None,
    ) -> io.NodeOutput:
        def _prep(td):
            masks_bool = _unpack(td)
            if sort_by != "none" and masks_bool is not None:
                cx, area = _first_frame_cx_area(masks_bool)
                if sort_by == "left_to_right":
                    order = sorted(range(len(cx)), key=lambda i: cx[i])
                else:
                    order = sorted(range(len(area)), key=lambda i: -area[i])
                td = _subset_track_data(td, order)
            if object_indices.strip():
                indices = [int(i.strip()) for i in object_indices.split(",") if i.strip().isdigit()]
                packed = td.get("packed_masks")
                n_obj = packed.shape[1] if packed is not None else 0
                indices = [i for i in indices if 0 <= i < n_obj]
                td = _subset_track_data(td, indices)
            return td

        drv = _prep(driving_track_data)

        # Animation: driving=black, ref/prefix=white. Replacement: driving=white, ref/prefix=black.
        mask_video = _render_colored_masks(drv, "white" if replacement_mode else "black", render_device)
        ref_bg = "black" if replacement_mode else "white"
        prefix_bg = "black" if replacement_mode else "white"

        if ref_track_data is not None:
            ref = _prep(ref_track_data)
            reference_image_mask = _render_colored_masks(ref, ref_bg, render_device)
        else:
            height, width = drv["orig_size"]
            reference_image_mask = _blank_images(1, height, width, ref_bg, render_device)

        if prefix_track_data is not None:
            prefix = _prep(prefix_track_data)
            prefix_image_mask = _render_prefix_image_masks(
                prefix,
                prefix_bg,
                prefix_mask_mode,
                render_device=render_device,
            )
            if not _has_any_mask(prefix.get("packed_masks"), _render_device(render_device)):
                LOGGER.warning(
                    "SCAIL2ColoredMaskV2: prefix_image_mask contains only the %s background. "
                    "Check the prefix SAM3 track input, prompt, threshold, or initial mask.",
                    prefix_bg,
                )
        else:
            height, width = drv["orig_size"]
            LOGGER.warning("SCAIL2ColoredMaskV2: prefix_track_data is not connected; prefix_image_mask is blank.")
            prefix_image_mask = _blank_images(1, height, width, prefix_bg, render_device)

        return io.NodeOutput(mask_video, reference_image_mask, prefix_image_mask)


class AutoRefCollage(io.ComfyNode):
    """Extract up to 5 reference people with SAM3 and compose an automatic collage."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="AutoRefCollage",
            display_name="多参图像自动拼接",
            category="image/compositing",
            search_aliases=["auto reference collage", "person collage", "sam3 collage", "multi reference"],
            inputs=[
                io.Model.Input(
                    "model",
                    display_name="model",
                    tooltip="SAM3/SAM3.1 model from CheckpointLoaderSimple.",
                ),
                io.Clip.Input(
                    "clip",
                    display_name="clip",
                    tooltip="SAM3/SAM3.1 CLIP from CheckpointLoaderSimple. The node encodes its internal prompt with this input.",
                ),
                io.Image.Input("image_1", display_name="image_1", optional=True),
                io.Image.Input("image_2", display_name="image_2", optional=True),
                io.Image.Input("image_3", display_name="image_3", optional=True),
                io.Image.Input("image_4", display_name="image_4", optional=True),
                io.Image.Input("image_5", display_name="image_5", optional=True),
                io.String.Input(
                    "prompt",
                    display_name="prompt",
                    default="person",
                    multiline=True,
                    tooltip="Text prompt used internally for SAM3 detection. Use a short object phrase, e.g. person or woman.",
                ),
                io.Int.Input(
                    "width",
                    display_name="width",
                    default=1280,
                    min=64,
                    max=8192,
                    step=8,
                    tooltip="Output collage width.",
                ),
                io.Int.Input(
                    "height",
                    display_name="height",
                    default=1280,
                    min=64,
                    max=8192,
                    step=8,
                    tooltip="Output collage height.",
                ),
                io.Float.Input(
                    "detection_threshold",
                    display_name="detection_threshold",
                    default=0.5,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    tooltip="SAM3 mask threshold after segmentation. Lower values keep more edge/detail; higher values remove weak regions.",
                ),
                io.Combo.Input(
                    "background",
                    display_name="background",
                    options=["white", "black"],
                    default="white",
                    tooltip="Background color for the RGB collage image output.",
                ),
            ],
            outputs=[
                io.Image.Output("collage"),
                io.Mask.Output("alpha_mask"),
            ],
            is_experimental=True,
        )

    @classmethod
    def execute(
        cls,
        model,
        clip,
        image_1=None,
        image_2=None,
        prompt="person",
        width=1280,
        height=1280,
        detection_threshold=0.5,
        background="white",
        image_3=None,
        image_4=None,
        image_5=None,
    ) -> io.NodeOutput:
        images = [
            img
            for img in (
                _first_batch_frame(image_1),
                _first_batch_frame(image_2),
                _first_batch_frame(image_3),
                _first_batch_frame(image_4),
                _first_batch_frame(image_5),
            )
            if img is not None
        ]
        if not images:
            collage, alpha_mask = _blank_collage_output(int(width), int(height), background)
            return io.NodeOutput(collage, alpha_mask)

        threshold = max(0.0, min(float(detection_threshold), 1.0))
        conditioning = _encode_sam3_prompt(clip, prompt)
        cutouts = []
        pbar = comfy.utils.ProgressBar(len(images))
        for image in images:
            alpha = _segment_person_with_sam3(
                model,
                image,
                prompt,
                conditioning,
                threshold,
            )
            cutouts.append(_prepare_cutout(image, alpha.to(image.device)))
            pbar.update(1)

        collage, alpha_mask = _compose_collage(cutouts, int(width), int(height), background)
        return io.NodeOutput(collage, alpha_mask)


class ManualRefCollage(io.ComfyNode):
    """Extract up to 5 reference people with SAM3 and compose using a saved manual layout."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ManualRefCollage",
            display_name="多参图像手动拼接",
            category="image/compositing",
            search_aliases=["manual reference collage", "sam3 manual collage", "multi reference"],
            inputs=[
                io.Model.Input(
                    "model",
                    display_name="model",
                    tooltip="SAM3/SAM3.1 model from CheckpointLoaderSimple.",
                ),
                io.Clip.Input(
                    "clip",
                    display_name="clip",
                    tooltip="SAM3/SAM3.1 CLIP from CheckpointLoaderSimple. The node encodes the prompt with this input.",
                ),
                io.Image.Input("image_1", display_name="image_1", optional=True),
                io.Image.Input("image_2", display_name="image_2", optional=True),
                io.Image.Input("image_3", display_name="image_3", optional=True),
                io.Image.Input("image_4", display_name="image_4", optional=True),
                io.Image.Input("image_5", display_name="image_5", optional=True),
                io.Image.Input("video_frame", display_name="video_frame", optional=True),
                io.String.Input(
                    "prompt",
                    display_name="prompt",
                    default="person",
                    multiline=True,
                    tooltip="Text prompt used internally for SAM3 detection. Use a short object phrase, e.g. person or woman.",
                ),
                io.String.Input(
                    "layout_json",
                    display_name="layout_json",
                    default="",
                    multiline=True,
                    tooltip="Internal manual collage layout saved by the node UI.",
                ),
                io.Int.Input(
                    "width",
                    display_name="width",
                    default=1280,
                    min=64,
                    max=8192,
                    step=8,
                    tooltip="Output collage width.",
                ),
                io.Int.Input(
                    "height",
                    display_name="height",
                    default=1280,
                    min=64,
                    max=8192,
                    step=8,
                    tooltip="Output collage height.",
                ),
                io.Float.Input(
                    "detection_threshold",
                    display_name="detection_threshold",
                    default=0.5,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    tooltip="SAM3 mask threshold after segmentation. Lower values keep more edge/detail; higher values remove weak regions.",
                ),
                io.Float.Input(
                    "background_opacity",
                    display_name="background_opacity",
                    default=0.3,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    tooltip="Background video frame opacity mixed over the black/white collage background.",
                ),
                io.Combo.Input(
                    "background",
                    display_name="background",
                    options=["black", "white"],
                    default="black",
                    tooltip="Background color for the RGB collage image output.",
                ),
            ],
            outputs=[
                io.Image.Output("collage"),
                io.Mask.Output("alpha_mask"),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.extra_pnginfo],
            is_experimental=True,
        )

    @classmethod
    def execute(
        cls,
        model,
        clip,
        image_1=None,
        image_2=None,
        video_frame=None,
        prompt="person",
        layout_json="",
        width=1280,
        height=1280,
        detection_threshold=0.5,
        background_opacity=0.3,
        background="black",
        image_3=None,
        image_4=None,
        image_5=None,
    ) -> io.NodeOutput:
        raw_images = [image_1, image_2, image_3, image_4, image_5]
        hidden = getattr(cls, "hidden", None)
        extra_pnginfo = getattr(hidden, "extra_pnginfo", None)
        unique_id = getattr(hidden, "unique_id", None)
        width = _workflow_linked_numeric_input(extra_pnginfo, unique_id, "width", width)
        height = _workflow_linked_numeric_input(extra_pnginfo, unique_id, "height", height)
        image_slots = [
            _first_batch_frame(image) if _workflow_input_is_active(extra_pnginfo, unique_id, f"image_{index + 1}") else None
            for index, image in enumerate(raw_images)
        ]
        out_width, out_height, out_background, _ = _parse_manual_layout(
            layout_json,
            len(image_slots),
            int(width),
            int(height),
            background,
            use_layout_size=False,
        )
        image_count = sum(image is not None for image in image_slots)
        if image_count == 0:
            collage, alpha_mask = _blank_collage_output(out_width, out_height, out_background)
            return io.NodeOutput(collage, alpha_mask)

        threshold = max(0.0, min(float(detection_threshold), 1.0))
        conditioning = _encode_sam3_prompt(clip, prompt)
        cutouts = [None] * len(image_slots)
        pbar = comfy.utils.ProgressBar(image_count)
        for index, image in enumerate(image_slots):
            if image is None:
                continue
            alpha = _segment_person_with_sam3(
                model,
                image,
                prompt,
                conditioning,
                threshold,
            )
            cutouts[index] = _prepare_cutout(image, alpha.to(image.device))
            pbar.update(1)

        collage, alpha_mask = _compose_manual_collage(
            cutouts,
            out_width,
            out_height,
            out_background,
            layout_json,
            use_layout_size=False,
        )
        return io.NodeOutput(collage, alpha_mask)


class ComfySwitchNodeV2(io.ComfyNode):
    """Switch node variant that only requires the selected branch to be connected."""

    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template("switch")
        return io.Schema(
            node_id="ComfySwitchNodeV2",
            display_name="Switch V2",
            category="utilities/logic",
            is_experimental=True,
            inputs=[
                io.Boolean.Input("switch"),
                io.MatchType.Input("on_false", template=template, display_name="false", lazy=True, optional=True),
                io.MatchType.Input("on_true", template=template, display_name="true", lazy=True, optional=True),
            ],
            outputs=[
                io.MatchType.Output(template=template, display_name="output"),
            ],
        )

    @classmethod
    def check_lazy_status(cls, switch, on_false=MISSING, on_true=MISSING):
        if switch and on_true is None:
            return ["on_true"]
        if not switch and on_false is None:
            return ["on_false"]

    @classmethod
    def validate_inputs(cls, switch, on_false=MISSING, on_true=MISSING):
        if switch and on_true is MISSING:
            return "请在true接口接上相关节点。"
        if not switch and on_false is MISSING:
            return "请在false接口接上相关节点。"
        return True

    @classmethod
    def execute(cls, switch, on_true=MISSING, on_false=MISSING) -> io.NodeOutput:
        if switch:
            if on_true is MISSING:
                raise ValueError("请在true接口接上相关节点。")
            return io.NodeOutput(on_true)
        if on_false is MISSING:
            raise ValueError("请在false接口接上相关节点。")
        return io.NodeOutput(on_false)


class InvertBoolean(io.ComfyNode):
    """Invert a BOOLEAN value from nodes such as PrimitiveBoolean."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="InvertBoolean",
            display_name="Invert Boolean",
            category="utilities/logic",
            search_aliases=["反转布尔值", "invert boolean", "not", "toggle", "negate", "flip boolean"],
            inputs=[
                io.Boolean.Input(
                    "boolean",
                    display_name="boolean",
                    force_input=True,
                    tooltip="BOOLEAN input to invert.",
                ),
            ],
            outputs=[
                io.Boolean.Output("boolean", display_name="boolean"),
            ],
        )

    @classmethod
    def execute(cls, boolean: bool) -> io.NodeOutput:
        return io.NodeOutput(not boolean)


class ImageBatchMultiV2(io.ComfyNode):
    """KJNodes ImageBatchMulti variant that skips missing inputs instead of outputting black frames."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ImageBatchMultiV2",
            display_name="Image Batch Multi V2",
            category="image/batch",
            description=(
                "Creates an image batch from multiple image inputs. "
                "Unlike KJNodes ImageBatchMulti, missing or bypassed inputs are skipped instead of being replaced by black frames."
            ),
            search_aliases=["图像组合批次（多重）V2", "image batch multi v2", "image batch multi", "combine image batch multi"],
            accept_all_inputs=True,
            inputs=[
                io.Int.Input("inputcount", default=2, min=2, max=1000, step=1),
                io.Image.Input("image_1", optional=True),
                io.Image.Input("image_2", optional=True),
            ],
            outputs=[
                io.Image.Output("images", display_name="images"),
            ],
        )

    @staticmethod
    def _valid_image(value):
        return isinstance(value, torch.Tensor) and value.ndim == 4 and value.shape[0] > 0

    @classmethod
    def execute(cls, inputcount: int, image_1=None, image_2=None, **kwargs) -> io.NodeOutput:
        kwargs["image_1"] = image_1
        kwargs["image_2"] = image_2
        images = [
            kwargs.get(f"image_{index}")
            for index in range(1, int(inputcount) + 1)
            if cls._valid_image(kwargs.get(f"image_{index}"))
        ]
        if not images:
            return io.NodeOutput(None)

        first = images[0]
        h, w = first.shape[1], first.shape[2]
        max_ch = max(image.shape[-1] for image in images)
        total_frames = sum(image.shape[0] for image in images)

        out = torch.empty((total_frames, h, w, max_ch), dtype=first.dtype, device=first.device)
        offset = 0
        for image in images:
            if image.shape[1:3] != (h, w):
                image = comfy.utils.common_upscale(
                    image.movedim(-1, 1),
                    w,
                    h,
                    "bilinear",
                    "center",
                ).movedim(1, -1)
            if image.shape[-1] < max_ch:
                image = F.pad(image, (0, max_ch - image.shape[-1]), mode="constant", value=1.0)

            n = image.shape[0]
            out[offset:offset + n].copy_(image.to(device=out.device, dtype=out.dtype), non_blocking=True)
            offset += n

        return io.NodeOutput(out.cpu())


class FastGroupsBypassSwitch(io.ComfyNode):
    """Two-route switch node that also drives workflow group bypass/enable state from the frontend."""

    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template("fast_groups_bypass_switch")
        return io.Schema(
            node_id="FastGroupsBypassSwitch",
            display_name="多框忽略并切换",
            category="utilities/logic",
            search_aliases=["fast groups bypass switch", "group bypass switch", "多框忽略并切换"],
            is_experimental=True,
            inputs=[
                io.MatchType.Input("input1", template=template, display_name="input1", lazy=True, optional=True),
                io.MatchType.Input("input2", template=template, display_name="input2", lazy=True, optional=True),
            ],
            outputs=[
                io.MatchType.Output(template=template, display_name="output"),
            ],
            hidden=[io.Hidden.unique_id, io.Hidden.extra_pnginfo],
        )

    @staticmethod
    def _selected_group(value):
        try:
            parsed = int(value)
        except Exception:
            parsed = 1
        return 2 if parsed == 2 else 1

    @staticmethod
    def _group_label(name, fallback):
        text = str(name or "").strip()
        return text or fallback

    @staticmethod
    def _workflow_node(extra_pnginfo, unique_id):
        workflow = (extra_pnginfo or {}).get("workflow") if isinstance(extra_pnginfo, dict) else None
        nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
        if not isinstance(nodes, list):
            return {}
        wanted = str(unique_id)
        for node in nodes:
            if str(node.get("id")) == wanted:
                return node
        return {}

    @classmethod
    def _ui_state(cls, extra_pnginfo=None, unique_id=None):
        node = cls._workflow_node(extra_pnginfo, unique_id)
        properties = node.get("properties") if isinstance(node, dict) else {}
        if not isinstance(properties, dict):
            properties = {}
        return {
            "selected_group": cls._selected_group(properties.get("fh_selected_group", 1)),
            "group_1_name": cls._group_label(properties.get("fh_group_1_name", ""), "input1"),
            "group_2_name": cls._group_label(properties.get("fh_group_2_name", ""), "input2"),
        }

    @classmethod
    def check_lazy_status(
        cls,
        input1=MISSING,
        input2=MISSING,
    ):
        selected = cls._ui_state(cls.hidden.extra_pnginfo, cls.hidden.unique_id)["selected_group"]
        if selected == 1 and input1 is None:
            return ["input1"]
        if selected == 2 and input2 is None:
            return ["input2"]

    @classmethod
    def validate_inputs(
        cls,
        input1=MISSING,
        input2=MISSING,
    ):
        return True

    @classmethod
    def execute(
        cls,
        input1=MISSING,
        input2=MISSING,
    ) -> io.NodeOutput:
        state = cls._ui_state(cls.hidden.extra_pnginfo, cls.hidden.unique_id)
        selected = state["selected_group"]
        if selected == 1:
            if input1 is MISSING:
                raise ValueError(f"请在{cls._group_label(state['group_1_name'], 'input1')}接口接上相关节点。")
            return io.NodeOutput(input1)
        if input2 is MISSING:
            raise ValueError(f"请在{cls._group_label(state['group_2_name'], 'input2')}接口接上相关节点。")
        return io.NodeOutput(input2)


if PromptServer is not None:
    @PromptServer.instance.routes.post("/feihou/manual_collage/load")
    async def feihou_manual_collage_load(request):
        try:
            data = await request.json()
            prompt_data = data.get("prompt") or {}
            node_id = data.get("node_id")
            prompt = str(data.get("prompt_text") or "person").strip() or "person"
            image_names = list(data.get("images") or [])
            while len(image_names) < 5:
                image_names.append("")
            image_enabled = list(data.get("image_enabled") or [])
            while len(image_enabled) < 5:
                image_enabled.append(True)
            image_names = [
                ""
                if not _bool_enabled(image_enabled[index])
                else _normalize_media_name(image_names[index]) or _resolve_linked_media_name(prompt_data, node_id, f"image_{index + 1}")
                for index in range(5)
            ]
            video_enabled = _bool_enabled(data.get("video_frame_enabled"), True)
            video_name = (
                _normalize_media_name(data.get("video_frame")) or _resolve_linked_media_name(prompt_data, node_id, "video_frame")
            ) if video_enabled else ""

            previews = []
            ckpt_name = ""
            if any(image_names):
                ckpt_name = _resolve_checkpoint_from_prompt(prompt_data, node_id)
                if not ckpt_name:
                    return web.json_response({"success": False, "error": "未找到上游 CheckpointLoaderSimple 节点。"}, status=400)

                model, clip = _load_preview_model_and_clip(ckpt_name)
                conditioning = _encode_sam3_prompt(clip, prompt)
                threshold = max(0.0, min(float(data.get("detection_threshold", 0.5)), 1.0))

                for image_name in image_names:
                    if not image_name:
                        previews.append("")
                        continue
                    image = _load_input_image_from_name(image_name)
                    image = image.to(device=comfy.model_management.intermediate_device(), dtype=torch.float32)
                    alpha = _segment_person_with_sam3(model, image, prompt, conditioning, threshold)
                    cutout = _prepare_cutout(image, alpha.to(image.device))
                    previews.append(_tensor_rgba_to_data_url(cutout["rgb"], cutout["alpha"]))

            while len(previews) < 5:
                previews.append("")

            background_preview = ""
            if video_name:
                try:
                    background_frame = _load_media_first_frame_from_name(video_name)
                    background_preview = _tensor_rgb_to_data_url(background_frame)
                except Exception:
                    LOGGER.warning("ManualRefCollage background preview load skipped for %s", video_name, exc_info=True)

            return web.json_response({
                "success": True,
                "previews": previews,
                "background_preview": background_preview,
                "checkpoint": ckpt_name,
            })
        except Exception as exc:
            LOGGER.exception("ManualRefCollage preview load failed")
            return web.json_response({"success": False, "error": str(exc)}, status=500)


class FeiHouToolboxExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            SCAIL2ColoredMaskV2,
            AutoRefCollage,
            ManualRefCollage,
            ComfySwitchNodeV2,
            InvertBoolean,
            ImageBatchMultiV2,
            FastGroupsBypassSwitch,
        ]


async def comfy_entrypoint() -> FeiHouToolboxExtension:
    return FeiHouToolboxExtension()
