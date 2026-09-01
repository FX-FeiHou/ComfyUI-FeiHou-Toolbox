"""Exact VHS Video Combine execution with one final metadata-bearing video."""

import copy
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from comfy.cli_args import args
from comfy_api.latest import io
from .vhs_compat.nodes import VideoCombine as _VHSVideoCombine
from .vhs_compat.nodes import get_video_formats as _get_video_formats
# Register the same VHS preview/query endpoints used by the copied frontend.
from .vhs_compat import server as _vhs_server  # noqa: F401

VHSBatchManager = io.Custom("VHS_BatchManager")
VHSFilenames = io.Custom("VHS_FILENAMES")
FORMAT_DIRECTORY = Path(__file__).with_name("video_formats")


def _ffmpeg_path():
    forced = os.environ.get("VHS_FORCE_FFMPEG_PATH")
    if forced:
        return forced
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _write_ffmetadata(metadata, path):
    def escape(key, value):
        text = json.dumps(value, ensure_ascii=False)
        text = text.replace("\\", "\\\\").replace(";", "\\;").replace("#", "\\#")
        text = text.replace("=", "\\=").replace("\n", "\\\n")
        return f"{key}={text}"

    with open(path, "w", encoding="utf-8") as stream:
        stream.write(";FFMETADATA1\n")
        for key in ("prompt", "workflow"):
            if key in metadata:
                stream.write(escape(key, metadata[key]) + "\n")
        for key, value in metadata.items():
            if key not in {"prompt", "workflow"}:
                stream.write(escape(key, value) + "\n")


class VideoCombineV2(io.ComfyNode):
    """Original VHS Video Combine, with only its final-file policy changed."""

    @classmethod
    def define_schema(cls):
        # Use the original VHS format discovery and its widget definitions.
        ffmpeg_formats, format_widgets = _get_video_formats()
        format_widgets["image/webp"] = [["lossless", "BOOLEAN", {"default": True}]]
        return io.Schema(
            node_id="VideoCombineV2",
            display_name="Video Combine 🎥🅥🅗🅢 V2",
            category="Video Helper Suite 🎥🅥🅗🅢",
            description="Exact VideoHelperSuite Video Combine with a single final audio video containing ComfyUI metadata.",
            search_aliases=["video combine v2", "video combine", "VHS video combine", "视频合并 V2", "视频合并"],
            inputs=[
                io.MultiType.Input(io.Image.Input("images"), [io.Image, io.Latent]),
                io.Audio.Input("audio", optional=True),
                VHSBatchManager.Input("meta_batch", display_name="meta_batch", optional=True),
                io.Vae.Input("vae", optional=True),
                # Older/newer ComfyUI frontends do not always serialize custom
                # numeric widgets.  These must therefore be optional inputs
                # with Python defaults: a missing widget value is never a
                # validation error, while a linked value still overrides it.
                io.Float.Input("frame_rate", default=8.0, min=1.0, step=1.0, optional=True, socketless=True),
                io.Int.Input("loop_count", default=0, min=0, max=100, step=1, optional=True, socketless=True),
                io.String.Input("filename_prefix", default="AnimateDiff", optional=True, socketless=True),
                io.Combo.Input("format", options=["image/gif", "image/webp"] + ffmpeg_formats,
                               extra_dict={"formats": format_widgets}, optional=True, socketless=True),
                io.Boolean.Input("pingpong", default=False, optional=True, socketless=True),
                io.Boolean.Input("save_output", default=True, optional=True, socketless=True),
            ],
            outputs=[VHSFilenames.Output("Filenames")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
            is_output_node=True,
        )

    @staticmethod
    def _metadata(prompt, extra_pnginfo):
        if getattr(args, "disable_metadata", False):
            return {}
        metadata = dict(extra_pnginfo or {})
        if prompt is not None:
            metadata["prompt"] = prompt
        return metadata

    @staticmethod
    def _embed_metadata(final_path, metadata):
        if not metadata:
            return
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            raise ProcessLookupError("ffmpeg is required to embed ComfyUI metadata in Video Combine 🎥🅥🅗🅢 V2.")
        folder = os.path.dirname(final_path)
        suffix = Path(final_path).suffix
        metadata_path = os.path.join(folder, f".feihou-vhs-metadata-{uuid.uuid4().hex}.txt")
        replacement = os.path.join(folder, f".feihou-vhs-final-{uuid.uuid4().hex}{suffix}")
        _write_ffmetadata(metadata, metadata_path)
        command = [ffmpeg, "-v", "error", "-y", "-i", final_path, "-i", metadata_path,
                   "-map", "0", "-map_metadata", "1", "-c", "copy"]
        if suffix.lower() in {".mp4", ".m4v", ".mov"}:
            command += ["-movflags", "use_metadata_tags"]
        command.append(replacement)
        try:
            completed = subprocess.run(command, capture_output=True, check=False)
            if completed.returncode != 0:
                raise RuntimeError("ffmpeg could not embed ComfyUI metadata:\n" + completed.stderr.decode("utf-8", errors="replace"))
            os.replace(replacement, final_path)
        finally:
            for path in (metadata_path, replacement):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

    @classmethod
    def execute(cls, images, frame_rate=8.0, loop_count=0, filename_prefix="AnimateDiff",
                format="image/gif", pingpong=False, save_output=True, audio=None,
                meta_batch=None, vae=None, **format_values):
        # The original node writes this PNG solely for its workflow sidecar.
        # Disable it before the original function starts, rather than deleting it later.
        original_extra = cls.hidden.extra_pnginfo or {}
        extra_pnginfo = copy.deepcopy(original_extra)
        workflow = extra_pnginfo.setdefault("workflow", {})
        workflow.setdefault("extra", {})["VHS_MetadataImage"] = False
        # The original temporary silent encode must not remain in output after V2 finishes.
        workflow["extra"]["VHS_KeepIntermediate"] = False

        result = _VHSVideoCombine().combine_video(
            images=images,
            frame_rate=frame_rate,
            loop_count=loop_count,
            filename_prefix=filename_prefix,
            format=format,
            pingpong=pingpong,
            save_output=save_output,
            prompt=cls.hidden.prompt,
            extra_pnginfo=extra_pnginfo,
            audio=audio,
            unique_id=cls.hidden.unique_id,
            meta_batch=meta_batch,
            vae=vae,
            **format_values,
        )

        ui = result.get("ui", {})
        filenames = result.get("result", ((save_output, []),))[0]
        output_files = list(filenames[1])
        if not output_files:
            return io.NodeOutput((save_output, []), ui=ui)

        # VHS returns the audio mux result as its final entry when audio is used;
        # otherwise its original encode is already the final entry.
        final_path = output_files[-1]
        # GIF/WebP and frame-sequence formats have no reliable ffmpeg metadata
        # container.  Preserve the original VHS output for those formats rather
        # than trying to remux them as a video and turning a valid save into an
        # error.  The requested workflow metadata is embedded in video files.
        video_extensions = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
        if os.path.isfile(final_path) and Path(final_path).suffix.lower() in video_extensions:
            cls._embed_metadata(final_path, cls._metadata(cls.hidden.prompt, original_extra))

        # No PNG sidecar is created.  Remove every non-final original artifact,
        # including the silent video that VHS uses internally before its audio mux.
        for path in output_files[:-1]:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass

        preview = ui.get("gifs", [{}])[0]
        if preview:
            preview.pop("workflow", None)
            preview["filename"] = os.path.basename(final_path)
            preview["fullpath"] = final_path
        return io.NodeOutput((save_output, [final_path]), ui=ui)
