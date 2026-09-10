"""Image and video API nodes for the FeiHou AI API.

The nodes intentionally use one fixed provider endpoint.  This avoids turning
the model-refresh API into an arbitrary server-side request proxy, while still
letting the account's own API key determine the models that are available.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import torch
from PIL import Image

import comfy.utils
import comfy.model_management
from comfy_api.latest import InputImpl, io
from comfy_extras.nodes_video import save_video_preview
from .feihou_api_media import collect_media, prepare_media


API_BASE_URL = "https://api.fei-hou.net"
_TIMEOUT_SECONDS = 120
_POLL_INTERVAL_SECONDS = 5
_MAX_POLL_ATTEMPTS = 240
_RUNNING_STATES = {
    "", "created", "queued", "pending", "processing", "running",
    "in_progress", "in-progress", "not_start",
}
_SUCCESS_STATES = {"success", "succeeded", "completed", "complete", "done", "finished"}
_FAILURE_STATES = {"failed", "failure", "error", "cancelled", "canceled", "rejected"}


class FeiHouApiError(RuntimeError):
    """An upstream API error with credentials redacted."""


def _api_key_headers(api_key: str, content_type: str | None = "application/json") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _read_json_response(request: Request) -> dict[str, Any]:
    request.add_header("User-Agent", "Mozilla/5.0 ComfyUI-FeiHou-Toolbox")
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed HTTPS provider URL
            body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise FeiHouApiError(f"API request failed (HTTP {exc.code}): {detail}") from exc
    except URLError as exc:
        raise FeiHouApiError(f"Could not connect to the API service: {exc.reason}") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeiHouApiError("The API returned an invalid JSON response.") from exc
    if not isinstance(payload, dict):
        raise FeiHouApiError("The API returned an unexpected response shape.")
    return payload


def _request_json(path: str, api_key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    method = "POST" if payload is not None else "GET"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_BASE_URL}{path}",
        data=body,
        headers=_api_key_headers(api_key),
        method=method,
    )
    return _read_json_response(request)


def _multipart_body(fields: dict[str, str], image: torch.Tensor) -> tuple[bytes, str]:
    """Build the fixed provider's reference-image upload request."""
    image_bytes = _tensor_to_png(image)
    boundary = f"----FeiHouApi{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"),
            b"\r\n",
        ))
    chunks.extend((
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="reference.png"\r\n',
        b"Content-Type: image/png\r\n\r\n",
        image_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _request_multipart(path: str, api_key: str, fields: dict[str, str], image: torch.Tensor) -> dict[str, Any]:
    body, content_type = _multipart_body(fields, image)
    request = Request(
        f"{API_BASE_URL}{path}",
        data=body,
        headers=_api_key_headers(api_key, content_type),
        method="POST",
    )
    return _read_json_response(request)


def _upload_reference_image(api_key: str, image: torch.Tensor) -> str:
    """Upload a ComfyUI IMAGE and return FeiHou's temporary public URL."""
    response = _request_multipart("/v1/files/upload", api_key, {}, image)
    url = str(response.get("url") or "").strip()
    if not url and isinstance(response.get("data"), dict):
        url = str(response["data"].get("url") or "").strip()
    if not url.startswith(("https://", "http://")):
        raise FeiHouApiError("The API did not return a usable reference-image URL.")
    return url


def _upload_media(api_key, filename, data, content_type):
    boundary = "----FeiHouMedia" + uuid.uuid4().hex
    # Use a generated multipart filename; user filenames may contain quotes/newlines.
    extension = filename.rsplit(".", 1)[-1].lower()
    if not re.fullmatch(r"[a-z0-9]{1,8}", extension):
        extension = "bin"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="media.{extension}"\r\n'
            f'Content-Type: {content_type}\r\n\r\n').encode() + data + f"\r\n--{boundary}--\r\n".encode()
    result = _read_json_response(Request(API_BASE_URL + "/v1/files/upload", data=body,
        headers=_api_key_headers(api_key, f"multipart/form-data; boundary={boundary}"), method="POST"))
    url = result.get("url") or (result.get("data") or {}).get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise FeiHouApiError("Media upload did not return a URL.")
    return url


def _tensor_to_png(image: torch.Tensor) -> bytes:
    if not isinstance(image, torch.Tensor) or image.ndim != 4 or image.shape[0] < 1:
        raise ValueError("The reference image must be a non-empty IMAGE batch.")
    pixels = image[0, ..., :3].detach().cpu().clamp(0, 1).numpy()
    encoded = (pixels * 255.0).round().astype(np.uint8)
    output = BytesIO()
    Image.fromarray(encoded, mode="RGB").save(output, format="PNG")
    return output.getvalue()


def _status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("status", "state", "task_status"):
        value = payload.get(key)
        if value is not None:
            return str(value).strip().lower()
    for container in ("data", "result", "output"):
        value = payload.get(container)
        found = _status(value)
        if found:
            return found
    return ""


def _task_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("task_id", "taskId", "id", "request_id"):
        value = payload.get(key)
        if value:
            return str(value)
    for container in ("data", "result", "output"):
        found = _task_id(payload.get(container))
        if found:
            return found
    return ""


def _error_message(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("fail_reason", "failure_details", "message", "error", "detail"):
        value = payload.get(key)
        if value:
            text = _error_message(value)
            if text:
                return text
    for container in ("data", "result", "output"):
        text = _error_message(payload.get(container))
        if text:
            return text
    return ""


def _collect_urls(payload: Any, kinds: set[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.startswith(("https://", "http://")) and value not in seen:
            seen.add(value)
            found.append(value)

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
            return
        if not isinstance(value, dict):
            return
        direct_keys = {"url", "result_url", "download_url", "file_url"}
        direct_keys |= {"image_url", "imageUrl"} if "image" in kinds else set()
        direct_keys |= {"video_url", "videoUrl"} if "video" in kinds else set()
        for key in direct_keys:
            add(value.get(key))
        child_keys = {"data", "result", "output", "outputs", "files", "artifacts", "content", "metadata"}
        child_keys |= {"image", "images", "image_urls", "imageUrls"} if "image" in kinds else set()
        child_keys |= {"video", "videos"} if "video" in kinds else set()
        for key in child_keys:
            if key in value:
                walk(value[key], depth + 1)

    walk(payload)
    return found


def _collect_base64_images(payload: Any) -> list[str]:
    result: list[str] = []

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, dict):
            for key in ("b64_json", "base64", "image_base64", "imageBase64"):
                encoded = value.get(key)
                if isinstance(encoded, str) and encoded:
                    result.append(encoded.split(",", 1)[-1])
            for key in ("data", "result", "output", "outputs", "images", "image"):
                if key in value:
                    walk(value[key], depth + 1)

    walk(payload)
    return result


def _poll_task(endpoint: str, task_id: str, api_key: str, progress: comfy.utils.ProgressBar) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(_MAX_POLL_ATTEMPTS):
        if attempt:
            time.sleep(_POLL_INTERVAL_SECONDS)
        last = _request_json(f"{endpoint}/{task_id}", api_key)
        state = _status(last)
        progress.update_absolute(min(95, 15 + int((attempt + 1) * 80 / _MAX_POLL_ATTEMPTS)))
        if state in _FAILURE_STATES:
            raise FeiHouApiError(_error_message(last) or f"The API task failed ({state}).")
        if state in _SUCCESS_STATES:
            return last
        # Some synchronous-compatible implementations do not report a state,
        # but do return a finished URL immediately.
        if not state and (_collect_urls(last, {"image", "video"}) or _collect_base64_images(last)):
            return last
        if state and state not in _RUNNING_STATES:
            raise FeiHouApiError(_error_message(last) or f"The API returned an unknown task state: {state}")
    raise FeiHouApiError("The API task timed out. Please check the provider task history.")


def _download_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "ComfyUI-FeiHou-Toolbox"})
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - URL is returned by fixed provider
            return response.read()
    except (HTTPError, URLError) as exc:
        raise FeiHouApiError(f"Could not download the generated media: {exc}") from exc


def _image_tensor_from_bytes(image_bytes: bytes) -> torch.Tensor:
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        array = np.array(image).astype(np.float32) / 255.0
    except Exception as exc:
        raise FeiHouApiError("The API result was not a valid image file.") from exc
    return torch.from_numpy(array)[None, ...]


def _model_kind(model_id: str) -> str:
    """Fallback only: prefer the provider's explicit media tags."""
    m = model_id.lower()
    if any(token in m for token in ("-t2i", "-i2i", "image", "seedream", "nanobanana", "midjourney")):
        return "image"
    if any(token in m for token in ("-t2v", "-i2v", "-r2v", "video", "seedance", "hailuo",
                                    "kling", "vidu", "happyhorse", "minimax-h3", "feihou-upscaler")):
        return "video"
    return ""


def _model_records(payload: Any) -> list[tuple[str, str]]:
    records = []

    def walk(value, inherited=""):
        if isinstance(value, str):
            if value.strip():
                records.append((value.strip(), inherited))
        elif isinstance(value, list):
            for item in value:
                walk(item, inherited)
        elif isinstance(value, dict):
            model_id = value.get("model_name") or value.get("id") or value.get("model") or value.get("name")
            tags = value.get("tags", [])
            if isinstance(tags, str):
                tags = tags.lower().replace(";", ",").split(",")
            tags = {str(tag).strip().lower() for tag in tags or []}
            kind = inherited
            if tags.intersection({"text", "prompt"}):
                kind = "other"
            elif {"image", "video"}.issubset(tags):
                kind = "image,video"
            elif "image" in tags:
                kind = "image"
            elif "video" in tags:
                kind = "video"
            elif tags.intersection({"llm", "audio", "music", "text", "embedding", "3d"}):
                kind = "other"
            if isinstance(model_id, str) and model_id.strip():
                records.append((model_id.strip(), kind))
            for key in ("data", "models", "items", "image_models", "video_models"):
                if key in value:
                    walk(value[key], {"image_models": "image", "video_models": "video"}.get(key, kind))
    walk(payload)
    return records


def _documented_models() -> list[tuple[str, str]]:
    request = Request(API_BASE_URL + "/docs/llms.txt", headers={"User-Agent": "Mozilla/5.0 ComfyUI-FeiHou-Toolbox"})
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            doc = response.read().decode("utf-8")
    except (HTTPError, URLError, UnicodeDecodeError) as exc:
        raise FeiHouApiError("Could not read the official model documentation.") from exc
    if "## 模型列表" not in doc:
        raise FeiHouApiError("Official model documentation format changed.")
    section = doc.split("## 模型列表", 1)[1].split("## 价格与计费", 1)[0]
    records = []
    block = False
    include = False
    category = ""
    for line in section.splitlines():
        if line.startswith("```"):
            if not block:
                include = line.strip() in ("```", "```text")
            block = not block
            continue
        if not block:
            if line.startswith("#"):
                if "音频" in line or "Context IR" in line:
                    category = "other"
                elif "图片" in line and "视频" not in line:
                    category = "image"
                elif any(word in line for word in ("视频", "Kling", "Hailuo", "Vidu", "MiniMax", "Minimax", "FLUX")):
                    category = "video"
            continue
        if not include:
            continue
        for token in line.split("#", 1)[0].split():
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*[-_][A-Za-z0-9_.-]+", token):
                records.append((token, "other" if category == "other" else _model_kind(token) or category))
    return records


def list_models(api_key: str, kind: str = "") -> list[str]:
    """Merge account model IDs with the live public catalog; never use a short static list."""
    api_key = str(api_key or "").strip()
    if not api_key:
        raise FeiHouApiError("Enter an API key before refreshing the model list.")
    kind = str(kind or "").strip().lower()
    records = []
    failures = []
    try:
        records.extend(_documented_models())
    except FeiHouApiError as exc:
        failures.append(str(exc))
    for path in ("/v1/models", "/api/pricing"):
        try:
            # The public catalog requires no account credential.
            payload = _request_json(path, api_key) if path == "/v1/models" else _read_json_response(
                Request(API_BASE_URL + path, headers={"Accept": "application/json"}))
            if payload.get("success") is False or payload.get("error"):
                raise FeiHouApiError("The provider rejected the model-list request.")
            page = _model_records(payload)
            if not page:
                raise FeiHouApiError("The provider returned an empty model catalog.")
            records.extend(page)
        except FeiHouApiError as exc:
            if path == "/v1/models" and ("HTTP 401" in str(exc) or "HTTP 403" in str(exc)):
                raise FeiHouApiError("The API key was rejected. Check the key and its permissions.") from exc
            failures.append(str(exc))
    if not records:
        raise FeiHouApiError("Could not refresh models: " + "; ".join(failures))
    # Explicit catalog categories override name heuristics for the same model ID.
    categories = {}
    for model_id, media_kind in records:
        if media_kind or model_id not in categories:
            categories[model_id] = media_kind
    models = [model_id for model_id, category in categories.items()
              if not kind or kind in (category or _model_kind(model_id)).split(",")
              or not (category or _model_kind(model_id))]
    if not models:
        raise FeiHouApiError("The live catalog returned no models for this media type.")
    return sorted(models, key=str.casefold)


def _normalise_prompt(prompt: str) -> str:
    """The FeiHou image endpoint requires a prompt of at least five characters."""
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Enter a prompt before generating.")
    return prompt if len(prompt) >= 5 else f"{prompt}，高质量画面"


RATIOS = ["default", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "4:5", "5:4", "2:1", "1:2", "1:8", "8:1"]
IMAGE_RESOLUTIONS = ["default", "auto", "0.5k", "1k", "1.5k", "2k", "4k", "custom"]
VIDEO_RESOLUTIONS = ["default", "480p", "720p", "1080p", "2k", "4k", "native1080p", "native4k"]


def parameter_options(model: str, kind: str) -> dict[str, Any]:
    """One source for UI choices and request validation (FeiHou llms.txt)."""
    m = model.lower()
    options: dict[str, Any] = {"resolution": ["default"], "aspect_ratio": ["default"],
        "duration": ["default"], "custom_size": False, "output_format": False,
        "seed": False, "generate_audio": False, "return_last_frame": False}
    if kind == "image":
        ratios = RATIOS[1:10]
        if m.startswith(("seedream", "dola-seedream")):
            resolutions = ["1k", "2k", "custom"]
            if "layer-decomposition" in m:
                resolutions = ["auto", "1k", "1.5k", "2k"]
                ratios = []
            options.update(custom_size="custom" in resolutions, output_format=True)
        elif m.startswith("feihou-image-nb-2-lite") or m.startswith("feihou-image-nb-flash") or m.startswith("feihou-image-g2"):
            resolutions = ["1k"]
        elif m.startswith("feihou-image-nb-2"):
            resolutions = ["0.5k", "1k", "2k", "4k"]
            ratios = RATIOS[1:]
        elif m.startswith(("feihou-image-nb-pro", "feihou-image-g-v2")):
            resolutions = ["1k", "2k", "4k"]
        elif m.startswith(("qwen-image", "feihou-image-gk-v2-edit")):
            resolutions = ["1k", "2k"]
            options["seed"] = m.startswith("qwen-image")
        elif m.startswith("feihou-image-gk-v2"):
            resolutions = []
            ratios = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"]
        else:
            resolutions, ratios = [], []
        options.update(resolution=["default", *resolutions], aspect_ratio=["default", *ratios])
    else:
        ratios = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]
        durations: list[str] = []
        if m.startswith("seedance"):
            resolutions = VIDEO_RESOLUTIONS[1:]
            if "standard" not in m:
                resolutions = resolutions[:5]
            if "2.5" in m:
                resolutions = [v for v in resolutions if v != "native4k"]
            durations = ["-1", *map(str, range(4, 31 if "2.5" in m else 16))]
            options.update(seed=True, generate_audio=True, return_last_frame=True)
        elif m.startswith("feihou-video-gk"):
            resolutions = ["480p", "720p"]
            durations = list(map(str, range(6, 31)))
        elif m.startswith("feihou-video-v31"):
            resolutions, durations, ratios = ["720p", "1080p", "4k"], ["8"], ["16:9", "9:16"]
        elif m.startswith("feihou-video-g-omni"):
            resolutions = ["720p"]
            if "lowprice" in m:
                durations = ["4", "6", "8", "10"]
                if "1.1" in m:
                    resolutions = ["720p", "1080p", "4k"]
        else:
            resolutions, ratios = [], []
        options.update(resolution=["default", *resolutions], aspect_ratio=["default", *ratios], duration=["default", *durations])
    return options


def _generation_parameters(model, kind, resolution="default", aspect_ratio="default", duration="default",
                           width=1024, height=1024, output_format="default", seed=-1,
                           generate_audio="default", return_last_frame=False):
    options = parameter_options(model, kind)
    for key, value in (("resolution", resolution), ("aspect_ratio", aspect_ratio), ("duration", str(duration))):
        if value not in options[key]:
            raise FeiHouApiError(f"{model} does not support {key}={value}. Supported: {', '.join(options[key])}")
    body: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    m = model.lower()
    if kind == "image":
        if m.startswith(("seedream", "dola-seedream")):
            if resolution == "custom":
                if not (240 <= width <= 8192 and 240 <= height <= 8192):
                    raise FeiHouApiError("Custom width and height must be between 240 and 8192.")
                metadata.update(width=width, height=height)
            elif aspect_ratio != "default":
                # Seedream has no ratio field; send pixel dimensions without resolution,
                # because its resolution field takes precedence over width and height.
                a, b = map(int, aspect_ratio.split(":"))
                longest = 2048 if resolution == "2k" else 1024
                metadata.update(width=round(longest * a / max(a, b)), height=round(longest * b / max(a, b)))
            elif resolution != "default":
                metadata["resolution"] = resolution
            if output_format != "default":
                metadata["output_format"] = output_format
        else:
            if resolution != "default":
                metadata["resolution"] = resolution
            if aspect_ratio != "default":
                if m.startswith(("feihou-image-g2", "qwen-image")):
                    metadata["ratio"] = aspect_ratio
                elif m.startswith("feihou-image-gk-v2-edit"):
                    body["aspect_ratio"] = aspect_ratio
                else:
                    body["size"] = aspect_ratio
    else:
        if duration != "default":
            if "seedance-2.5" in m and str(duration) == "-1":
                metadata["duration"] = -1
            else:
                body["seconds"] = str(duration)
        if "lowprice" in m and m.startswith("feihou-video-g-omni"):
            if resolution != "default":
                body["resolution"] = resolution
            if aspect_ratio != "default":
                body["aspect_ratio"] = aspect_ratio
        else:
            if resolution != "default":
                metadata["resolution"] = resolution
            if aspect_ratio != "default":
                metadata["ratio"] = aspect_ratio
        if options["generate_audio"] and generate_audio != "default":
            metadata["generate_audio"] = generate_audio == "on"
        if options["return_last_frame"]:
            metadata["return_last_frame"] = bool(return_last_frame)
    if options["seed"]:
        metadata["seed"] = int(seed)
    if metadata:
        body["metadata"] = metadata
    return body


class FeiHouApiImage(io.ComfyNode):
    """Generate one image through the provider's OpenAI-compatible endpoint."""

    @classmethod
    def validate_inputs(cls, model):
        # Models are populated per account by the refresh button, not the initial schema.
        return True if str(model).strip() else "Refresh and select a model before generating."

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="FeiHouApiImage",
            display_name="FeiHou-API Images",
            category="FeiHou Toolbox/API",
            description="Generate an image through the FeiHou AI API.",
            search_aliases=["FeiHou API 生图", "API生图", "api image", "text to image"],
            inputs=[
                io.String.Input("api_key", default="", tooltip="Your FeiHou API key. It is sent only to api.fei-hou.net; do not share a workflow containing it."),
                io.Combo.Input("model", options=[""], default="", tooltip="Click Refresh models after entering the API key."),
                io.String.Input("prompt", default="", multiline=True),
                io.AnyType.Input("media", optional=True, tooltip="Connect FeiHou-API Media, or a native IMAGE batch, VIDEO or AUDIO."),
                io.Combo.Input("resolution", options=IMAGE_RESOLUTIONS, default="default", optional=True),
                io.Combo.Input("aspect_ratio", options=RATIOS, default="default", optional=True),
                io.Int.Input("width", default=1024, min=240, max=8192, optional=True),
                io.Int.Input("height", default=1024, min=240, max=8192, optional=True),
                io.Combo.Input("output_format", options=["default", "png", "jpeg"], default="default", optional=True),
                io.Int.Input("seed", default=-1, min=-1, max=2147483647, optional=True, control_after_generate=False),
                io.String.Input("media_files", default="[]", optional=True),
            ],
            outputs=[io.Image.Output("image"), io.String.Output("image_url")],
        )

    @classmethod
    def execute(cls, api_key: str, model: str, prompt: str, image=None,
                resolution="default", aspect_ratio="default", width=1024, height=1024,
                output_format="default", seed=-1, media=None, media_files="[]") -> io.NodeOutput:
        api_key = str(api_key or "").strip()
        model = str(model or "").strip()
        prompt = _normalise_prompt(prompt)
        if not api_key:
            raise FeiHouApiError("Enter an API key.")
        if not model:
            raise FeiHouApiError("Refresh and select a model before generating.")
        progress = comfy.utils.ProgressBar(100)
        progress.update_absolute(5)
        request_body: dict[str, Any] = {"model": model, "prompt": prompt}
        request_body.update(_generation_parameters(model, "image", resolution, aspect_ratio,
            width=width, height=height, output_format=output_format, seed=seed))
        items = collect_media(media_files, media if media is not None else image)
        prepare_media(request_body, prompt, model, "image", items,
                      lambda name, data, mime: _upload_media(api_key, name, data, mime))
        result = _request_json("/v1/image/generations", api_key, request_body)
        urls = _collect_urls(result, {"image"})
        encoded = _collect_base64_images(result)
        task_id = _task_id(result)
        if not urls and not encoded and task_id:
            result = _poll_task("/v1/image/generations", task_id, api_key, progress)
            urls = _collect_urls(result, {"image"})
            encoded = _collect_base64_images(result)
        if not urls and not encoded:
            raise FeiHouApiError(_error_message(result) or "The image API returned no image result.")
        image_bytes = base64.b64decode(encoded[0]) if encoded else _download_bytes(urls[0])
        progress.update_absolute(100)
        return io.NodeOutput(_image_tensor_from_bytes(image_bytes), urls[0] if urls else "")


def _video_last_frame(payload: Any, video_bytes: bytes) -> torch.Tensor:
    """Prefer an explicitly returned tail image; otherwise decode only one frame at a time."""
    def find(value, depth=0):
        if depth > 8:
            return None
        if isinstance(value, dict):
            for key in ("last_frame_url", "lastFrameUrl", "last_frame", "lastFrame"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.startswith(("https://", "http://", "data:image/")):
                    return candidate
                if isinstance(candidate, dict):
                    for field in ("url", "image_url"):
                        url = candidate.get(field)
                        if isinstance(url, str) and url.startswith(("https://", "http://", "data:image/")):
                            return url
            for key in ("data", "result", "output", "outputs", "content", "metadata"):
                found = find(value.get(key), depth + 1)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = find(item, depth + 1)
                if found:
                    return found
        return None

    url = find(payload)
    if url:
        try:
            data = base64.b64decode(url.split(",", 1)[1]) if url.startswith("data:image/") else _download_bytes(url)
            return _image_tensor_from_bytes(data)
        except Exception:
            # Do not log signed URLs or provider response contents.
            logging.warning("[FeiHou] API tail image unavailable; extracting the final video frame.")
    import av
    last = None
    with av.open(BytesIO(video_bytes)) as container:
        for frame in container.decode(video=0):
            comfy.model_management.throw_exception_if_processing_interrupted()
            last = frame
        if last is None:
            raise FeiHouApiError("The generated video contains no decodable frames.")
        pixels = last.to_ndarray(format="rgb24")
    return torch.from_numpy(pixels.astype(np.float32) / 255.0).unsqueeze(0)


class FeiHouApiVideo(io.ComfyNode):
    """Generate one video and expose it as ComfyUI's native VIDEO type."""

    @classmethod
    def validate_inputs(cls, model):
        return True if str(model).strip() else "Refresh and select a model before generating."

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="FeiHouApiVideo",
            display_name="FeiHou-API Video",
            category="FeiHou Toolbox/API",
            description="Generate a video through the FeiHou AI API.",
            search_aliases=["FeiHou API 生视频", "API生视频", "api video", "text to video", "image to video"],
            inputs=[
                io.String.Input("api_key", default="", tooltip="Your FeiHou API key. It is sent only to api.fei-hou.net; do not share a workflow containing it."),
                io.Combo.Input("model", options=[""], default="", tooltip="Click Refresh models after entering the API key."),
                io.String.Input("prompt", default="", multiline=True),
                io.AnyType.Input("media", optional=True, tooltip="Connect FeiHou-API Media, or a native IMAGE batch, VIDEO or AUDIO."),
                io.Combo.Input("resolution", options=VIDEO_RESOLUTIONS, default="default", optional=True),
                io.Combo.Input("aspect_ratio", options=RATIOS, default="default", optional=True),
                io.Combo.Input("duration", options=["default", "-1", *map(str, range(2, 31))], default="default", optional=True),
                io.Int.Input("seed", default=-1, min=-1, max=2147483647, optional=True, control_after_generate=False),
                io.Combo.Input("generate_audio", options=["default", "on", "off"], default="default", optional=True),
                io.Boolean.Input("return_last_frame", default=False, optional=True, tooltip="Ask supported models for a tail image. If none is returned, the last frame output is extracted from the video."),
                io.String.Input("media_files", default="[]", optional=True),
            ],
            outputs=[io.Video.Output("video"), io.String.Output("video_url"), io.Image.Output("last_frame")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, api_key: str, model: str, prompt: str, image=None,
                resolution="default", aspect_ratio="default", duration="default", seed=-1,
                generate_audio="default", return_last_frame=False, media=None, media_files="[]") -> io.NodeOutput:
        api_key = str(api_key or "").strip()
        model = str(model or "").strip()
        prompt = _normalise_prompt(prompt)
        if not api_key:
            raise FeiHouApiError("Enter an API key.")
        if not model:
            raise FeiHouApiError("Refresh and select a model before generating.")
        progress = comfy.utils.ProgressBar(100)
        progress.update_absolute(5)
        request_body: dict[str, Any] = {"model": model, "prompt": prompt}
        request_body.update(_generation_parameters(model, "video", resolution, aspect_ratio,
            duration=duration, seed=seed, generate_audio=generate_audio, return_last_frame=return_last_frame))
        items = collect_media(media_files, media if media is not None else image)
        prepare_media(request_body, prompt, model, "video", items,
                      lambda name, data, mime: _upload_media(api_key, name, data, mime))
        result = _request_json("/v1/videos", api_key, request_body)
        urls = _collect_urls(result, {"video"})
        task_id = _task_id(result)
        if not urls and task_id:
            result = _poll_task("/v1/videos", task_id, api_key, progress)
            urls = _collect_urls(result, {"video"})
        if not urls:
            raise FeiHouApiError(_error_message(result) or "The video API returned no video result.")
        progress.update_absolute(100)
        video_bytes = _download_bytes(urls[0])
        video = InputImpl.VideoFromFile(BytesIO(video_bytes))
        last_frame = _video_last_frame(result, video_bytes)
        # Native VIDEO outputs do not require VideoHelperSuite.  A temporary
        # ComfyUI preview is created solely for the node UI, never output save.
        return io.NodeOutput(video, urls[0], last_frame, ui=save_video_preview(video))


async def fetch_models_for_route(api_key: str, kind: str = "") -> list[str]:
    """Keep the aiohttp route responsive while the upstream request runs."""
    return await asyncio.to_thread(list_models, api_key, kind)
