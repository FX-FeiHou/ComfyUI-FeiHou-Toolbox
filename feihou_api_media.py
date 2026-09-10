"""Embedded media records and native Comfy inputs for the FeiHou API nodes."""
import json
import mimetypes
import re
import wave
from io import BytesIO
from pathlib import Path

import folder_paths
import numpy as np
import torch
from PIL import Image
from comfy_api.latest import io

LIMITS = {"image": 9, "video": 3, "audio": 3}
EXTENSIONS = {
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"},
    "video": {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"},
    "audio": {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"},
}


def read_media_records(serialized):
    records = json.loads(serialized or "[]")
    if not isinstance(records, list) or len(records) > 15:
        raise ValueError("Media must contain at most 9 images, 3 videos and 3 audio files.")
    seen = set()
    result = []
    for record in records:
        kind, ordinal = record.get("media_type"), int(record.get("ordinal", 0))
        if kind not in LIMITS or not 1 <= ordinal <= LIMITS[kind] or (kind, ordinal) in seen:
            raise ValueError("Invalid or duplicate media slot.")
        seen.add((kind, ordinal))
        storage = record.get("storage", "input")
        roots = {"input": folder_paths.get_input_directory(), "temp": folder_paths.get_temp_directory(),
                 "output": folder_paths.get_output_directory()}
        if storage not in roots:
            raise ValueError("Invalid media storage location.")
        root = Path(roots[storage]).resolve()
        path = (root / record.get("subfolder", "") / record.get("filename", "")).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in EXTENSIONS[kind]:
            raise ValueError(f"Media file is missing or invalid: {kind} {ordinal}")
        result.append((kind, ordinal, path))
    return sorted(result, key=lambda item: (list(LIMITS).index(item[0]), item[1]))


def collect_media(serialized, media=None):
    """Resolve files before spending any upload or generation requests."""
    if isinstance(media, dict) and "feihou_media_files" in media:
        serialized, media = media["feihou_media_files"], None
    items = [(k, i, p.name, p) for k, i, p in read_media_records(serialized)]
    trims = {int(r["ordinal"]): r.get("audio_trim", "00:00-00:00")
             for r in json.loads(serialized or "[]") if r["media_type"] == "audio"}
    for index, (kind, ordinal, name, path) in enumerate(items):
        if kind == "audio":
            start, end = parse_audio_trim(trims.get(ordinal, "00:00-00:00"))
            if start or end:
                items[index] = (kind, ordinal, "trimmed.wav", (path, start, end))

    def add(kind, name, value):
        used = {i for k, i, _, _ in items if k == kind}
        free = next((i for i in range(1, LIMITS[kind] + 1) if i not in used), None)
        if free is None:
            raise ValueError(f"At most {LIMITS[kind]} {kind} inputs are supported.")
        items.append((kind, free, name, value))

    def visit(value):
        if value is None:
            return
        if isinstance(value, torch.Tensor):
            if value.ndim != 4 or value.shape[-1] not in (1, 3, 4):
                raise ValueError("Media tensor must be a ComfyUI IMAGE batch.")
            for frame in value:
                add("image", "reference.png", frame)
        elif isinstance(value, dict) and "waveform" in value and "sample_rate" in value:
            add("audio", "reference.wav", value)
        elif hasattr(value, "save_to") and hasattr(value, "get_components"):
            add("video", "reference.mp4", value)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
        else:
            raise ValueError("Media input accepts IMAGE, VIDEO, AUDIO or a list of these values.")
    visit(media)
    return sorted(items, key=lambda item: (list(LIMITS).index(item[0]), item[1]))


def parse_audio_trim(text):
    def seconds(value):
        if not re.fullmatch(r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?", value.strip()):
            raise ValueError("Audio trim must use start-end, e.g. 00:02-00:10.")
        total = 0.0
        for part in value.strip().split(":"):
            total = total * 60 + float(part)
        return total
    parts = str(text).split("-")
    if len(parts) != 2:
        raise ValueError("Audio trim must use start-end, e.g. 00:02-00:10.")
    start, end = map(seconds, parts)
    if end and end <= start:
        raise ValueError("Audio trim end must be after its start (or zero for the end of the file).")
    return start, end


class FeiHouApiMediaLoader(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="FeiHouApiMediaLoader", display_name="FeiHou-API Media",
            category="FeiHou Toolbox/API", description="Load 9 images, 3 videos and 3 audio files for FeiHou API nodes.",
            inputs=[io.String.Input("media_files", default="[]")],
            outputs=[io.Custom("FEIHOU_API_MEDIA").Output("media")])

    @classmethod
    def execute(cls, media_files="[]"):
        read_media_records(media_files)
        return io.NodeOutput({"feihou_media_files": media_files})

    @classmethod
    def fingerprint_inputs(cls, media_files="[]"):
        return [(k, i, str(path), path.stat().st_mtime_ns, path.stat().st_size)
                for k, i, path in read_media_records(media_files)]


def media_bytes(kind, value):
    if kind == "audio" and isinstance(value, tuple):
        from comfy_extras.nodes_audio import load
        path, start, end = value
        waveform, rate = load(str(path))
        first = int(start * rate)
        last = min(int(end * rate), waveform.shape[-1]) if end else waveform.shape[-1]
        if first >= last:
            raise ValueError("Audio trim starts beyond the end of the file.")
        value = {"waveform": waveform[..., first:last], "sample_rate": rate}
    if isinstance(value, Path):
        return value.read_bytes()
    buffer = BytesIO()
    if kind == "image":
        pixels = (value.detach().cpu().clamp(0, 1).numpy() * 255).round().astype(np.uint8)
        if pixels.shape[-1] == 1:
            pixels = pixels[..., 0]
        Image.fromarray(pixels).save(buffer, format="PNG")
    elif kind == "audio":
        waveform = value["waveform"]
        if waveform.ndim == 3:
            if waveform.shape[0] != 1:
                raise ValueError("Connect a single AUDIO batch.")
            waveform = waveform[0]
        samples = (waveform.detach().cpu().clamp(-1, 1).T.numpy() * 32767).astype("<i2")
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(waveform.shape[0])
            writer.setsampwidth(2)
            writer.setframerate(int(value["sample_rate"]))
            writer.writeframes(samples.tobytes())
    else:
        from comfy_api.latest import Types
        value.save_to(buffer, format=Types.VideoContainer.MP4)
    return buffer.getvalue()


def prepare_media(body, prompt, model, kind, items, upload):
    """Keep gallery ordinals stable while mapping them to submitted media order."""
    m = model.lower()
    counts = {k: sum(item[0] == k for item in items) for k in LIMITS}
    if m.startswith("seedance"):
        if m.endswith("-t2v") and items:
            raise ValueError("Seedance t2v accepts no references. Select an i2v or multi model.")
        if m.endswith("-i2v") and not 1 <= counts["image"] <= 2:
            raise ValueError("Seedance i2v requires 1 first-frame image and optionally 1 last-frame image.")
        if m.endswith("-multi") and not items:
            raise ValueError("Seedance multi requires at least one image, video or audio reference.")
    if m.startswith("qwen-image") and counts["image"] > 3:
        raise ValueError("This Qwen Image model accepts at most 3 reference images.")
    if kind == "image" and (counts["video"] or counts["audio"]):
        raise ValueError("This image API does not accept video or audio references. Remove those files or use a video model.")
    multimodal = (m.startswith("seedance") and m.endswith("-multi")) or m.startswith(("hailuo-h3", "minimax-h3-ow", "wan-3.0"))
    if counts["audio"] and not multimodal:
        raise ValueError(f"{model} does not support audio references through this node.")
    if counts["video"] and not (multimodal or m.startswith(("feihou-video-g-omni", "flux-3-video")) or "upscale" in m or "kling" in m):
        raise ValueError(f"{model} does not support video references through this node.")
    if counts["video"] > 1 and not multimodal:
        raise ValueError(f"{model} accepts only one video reference.")
    mapping = {}
    for media_kind in LIMITS:
        for index, item in enumerate((item for item in items if item[0] == media_kind), 1):
            mapping[(media_kind, item[1])] = index
    aliases = {"image": "image", "图片": "image", "图像": "image", "图": "image", "video": "video", "视频": "video", "audio": "audio", "音频": "audio"}
    labels = {"image": "图片", "video": "视频", "audio": "音频"}
    def replace(match):
        media_kind, ordinal = aliases[match[1].lower()], int(match[2])
        index = mapping.get((media_kind, ordinal))
        if index is None:
            raise ValueError(f"Prompt references an empty media slot: {match[0]}")
        return f"@{media_kind.title()} {index}" if m.startswith("seedance") else f"{labels[media_kind]}{index}"
    prompt = re.sub(r"@(image|video|audio|图片|图像|图|视频|音频)\s*(\d+)", replace, prompt, flags=re.I)
    urls = {k: [] for k in LIMITS}
    for media_kind, ordinal, filename, value in items:
        urls[media_kind].append(upload(filename, media_bytes(media_kind, value), mimetypes.guess_type(filename)[0] or "application/octet-stream"))
    if urls["image"]:
        body["images"] = urls["image"]
    metadata = body.setdefault("metadata", {})
    if m.startswith("seedance") and m.endswith("-multi"):
        metadata["content"] = [{"type": f"{k}_url", f"{k}_url": {"url": url}} for k in LIMITS for url in urls[k]]
        body.pop("images", None)
    elif multimodal:
        if urls["video"]:
            metadata["video_urls"] = urls["video"]
        if urls["audio"]:
            metadata["audio_urls"] = urls["audio"]
    else:
        if urls["video"]:
            metadata["video_url"] = urls["video"][0]
            if "lowprice" in m:
                body.pop("seconds", None)
    if not metadata:
        body.pop("metadata", None)
    body["prompt"] = prompt
