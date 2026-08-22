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

# V2 deliberately delegates the entire encode path to the installed original
# VideoHelperSuite node.  That preserves its formats, VAE batching, batch
# manager/requeue behavior, counters, and output logic without a reimplementation.
try:
    from videohelpersuite.nodes import VideoCombine as _VHSVideoCombine
    from videohelpersuite.nodes import get_video_formats as _get_video_formats
except ImportError as exc:  # pragma: no cover - surfaced clearly in ComfyUI
    raise ImportError(
        "Video Combine 🎥🅥🅗🅢 V2 requires ComfyUI-VideoHelperSuite, "
        "because it directly uses the original Video Combine implementation."
    ) from exc


VHSBatchManager = io.Custom("VHS_BatchManager")
VHSFilenames = io.Custom("VHS_FILENAMES")


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
                io.Float.Input("frame_rate", default=8.0, min=1.0, step=1.0),
                io.Int.Input("loop_count", default=0, min=0, max=100, step=1),
                io.String.Input("filename_prefix", default="AnimateDiff"),
                io.Combo.Input("format", options=["image/gif", "image/webp"] + ffmpeg_formats,
                               extra_dict={"formats": format_widgets}),
                io.Boolean.Input("pingpong", default=False),
                io.Boolean.Input("save_output", default=True),
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
    def execute(cls, images, frame_rate, loop_count, filename_prefix, format, pingpong,
                save_output, audio=None, meta_batch=None, vae=None, **format_values):
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
