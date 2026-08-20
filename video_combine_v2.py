"""VHS-compatible Video Combine with one-file audio and metadata output."""

import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from string import Template
from typing import Optional

import torch
from PIL import Image

import folder_paths
from comfy.cli_args import args
from comfy_api.latest import Input, InputImpl, io


VHSBatchManager = io.Custom("VHS_BatchManager")
FORMAT_DIRECTORY = Path(__file__).with_name("video_formats")
IMAGE_FORMATS = ["image/gif", "image/webp"]


def _flatten(items):
    result = []
    for item in items:
        result.extend(item if isinstance(item, list) else [item])
    return result


def _iterate_format(video_format, for_widgets=True):
    """The format-widget expansion used by VideoHelperSuite's JSON presets."""
    def indirector(container, key):
        value = container[key]
        if isinstance(value, list) and (
            not for_widgets or len(value) > 1 and not isinstance(value[1], dict)
        ):
            replacement = yield value
            if replacement is not None:
                container[key] = replacement
                yield

    for key in video_format:
        if key == "extra_widgets":
            if for_widgets:
                yield from video_format[key]
        elif key.endswith("_pass"):
            for index in range(len(video_format[key])):
                yield from indirector(video_format[key], index)
            if not for_widgets:
                video_format[key] = _flatten(video_format[key])
        else:
            yield from indirector(video_format, key)


def _apply_format_widgets(format_name, values):
    """Resolve a VHS JSON preset into concrete ffmpeg arguments."""
    preset_path = FORMAT_DIRECTORY / f"{format_name}.json"
    if not preset_path.is_file():
        raise ValueError(f"Video format preset was not found: {format_name}")
    with preset_path.open("r", encoding="utf-8") as stream:
        video_format = json.load(stream)

    for widget in _iterate_format(video_format):
        if widget[0] in values:
            continue
        if len(widget) > 2 and "default" in widget[2]:
            values[widget[0]] = widget[2]["default"]
        elif isinstance(widget[1], list):
            values[widget[0]] = widget[1][0]
        else:
            values[widget[0]] = {"BOOLEAN": False, "INT": 0, "FLOAT": 0, "STRING": ""}[widget[1]]

    iterator = _iterate_format(video_format, for_widgets=False)
    for value in iterator:
        while isinstance(value, list):
            if len(value) == 1:
                value = [Template(item).substitute(**values) for item in value[0]]
                break
            if isinstance(value[1], dict):
                value = value[1][str(values[value[0]])]
            elif len(value) > 3:
                value = Template(value[3]).substitute(val=values[value[0]])
            else:
                value = str(values[value[0]])
        iterator.send(value)
    return video_format


def _merge_filter_args(command, filter_type="-vf"):
    try:
        first = command.index(filter_type) + 1
        index = first
        while True:
            index = command.index(filter_type, index)
            command[first] += "," + command[index + 1]
            command.pop(index)
            command.pop(index)
    except ValueError:
        pass


def _ffmpeg_path():
    forced_path = os.environ.get("VHS_FORCE_FFMPEG_PATH")
    if forced_path:
        return forced_path
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _to_uint8_bytes(frame: torch.Tensor) -> bytes:
    return (frame.detach().cpu().clamp(0, 1).mul(255).add(0.5).to(torch.uint8).numpy()).tobytes()


def _to_uint16_bytes(frame: torch.Tensor) -> bytes:
    return (frame.detach().cpu().clamp(0, 1).mul(65535).add(0.5).to(torch.uint16).numpy()).tobytes()


def _expand_vhs_date_prefix(filename_prefix: str) -> str:
    """Resolve the same %date:yyyy-MM-dd% tokens VHS resolves in its web UI.

    This server-side fallback also supports API queues and workflows restored before
    the frontend extension has had a chance to serialize the widget value.
    """
    now = datetime.datetime.now()
    token_map = {
        "yyyy": f"{now.year:04d}", "yy": f"{now.year % 100:02d}",
        "MM": f"{now.month:02d}", "dd": f"{now.day:02d}",
        "hh": f"{now.hour:02d}", "mm": f"{now.minute:02d}", "ss": f"{now.second:02d}",
    }

    def replace(match):
        pattern = match.group(1)
        for token in ("yyyy", "yy", "MM", "dd", "hh", "mm", "ss"):
            pattern = pattern.replace(token, token_map[token])
        return pattern

    return re.sub(r"%date:([^%]+)%", replace, str(filename_prefix))


class VideoCombineV2(io.ComfyNode):
    """VHS Video Combine UI and presets, with a single final file when audio is connected."""

    @classmethod
    def _preset_names(cls):
        # Preserve the VHS list and ordering, while allowing later-added local presets too.
        preferred = [
            "16bit-png", "8bit-png", "av1-webm", "ffmpeg-gif", "ffv1-mkv", "gifski",
            "h264-mp4", "h265-mp4", "nvenc_av1-mp4", "nvenc_h264-mp4",
            "nvenc_hevc-mp4", "ProRes", "webm",
        ]
        available = {path.stem for path in FORMAT_DIRECTORY.glob("*.json")}
        return [name for name in preferred if name in available] + sorted(available.difference(preferred))

    @classmethod
    def _format_widgets(cls):
        widgets = {"image/webp": [["lossless", "BOOLEAN", {"default": True}]]}
        for preset_name in cls._preset_names():
            with (FORMAT_DIRECTORY / f"{preset_name}.json").open("r", encoding="utf-8") as stream:
                preset = json.load(stream)
            widgets[f"video/{preset_name}"] = list(_iterate_format(copy.deepcopy(preset)))
        return widgets

    @classmethod
    def define_schema(cls):
        formats = IMAGE_FORMATS + [f"video/{name}" for name in cls._preset_names()]
        return io.Schema(
            node_id="VideoCombineV2",
            display_name="Video Combine 🎥🅥🅗🅢 V2",
            category="Video Helper Suite 🎥🅥🅗🅢",
            description="VideoHelperSuite-compatible saver that writes audio and workflow metadata into one final file.",
            search_aliases=["video combine v2", "video combine", "VHS video combine", "视频合并 V2", "视频合并"],
            inputs=[
                # This is VHS's original IMAGE/LATENT multi-type input.  When a
                # VAE is connected the frontend switches this socket to LATENT.
                io.MultiType.Input(io.Image.Input("images", tooltip="Frames to encode, ordered by their batch index."), [io.Image, io.Latent]),
                io.Audio.Input("audio", optional=True, tooltip="Optional audio encoded into the one final file."),
                VHSBatchManager.Input("meta_batch", display_name="meta_batch", optional=True),
                io.Vae.Input("vae", optional=True),
                io.Float.Input("frame_rate", default=8.0, min=1.0, max=120.0, step=1.0),
                io.Int.Input("loop_count", default=0, min=0, max=100, step=1),
                io.String.Input("filename_prefix", default="AnimateDiff"),
                io.Combo.Input("format", options=formats, default="video/h264-mp4", extra_dict={"formats": cls._format_widgets()}),
                io.Boolean.Input("pingpong", default=False),
                io.Boolean.Input("save_output", default=True),
            ],
            outputs=[io.Video.Output("video")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @staticmethod
    def _prepare_frames(images: torch.Tensor, pingpong: bool, loop_count: int) -> torch.Tensor:
        if not isinstance(images, torch.Tensor) or images.ndim != 4 or images.shape[0] == 0:
            raise ValueError("images must be a non-empty IMAGE batch with shape [frames, height, width, channels].")
        frames = images
        if pingpong and frames.shape[0] > 2:
            frames = torch.cat((frames, torch.flip(frames[1:-1], dims=(0,))), dim=0)
        if loop_count > 0:
            frames = torch.cat([frames] * (int(loop_count) + 1), dim=0)
        return frames

    @classmethod
    def _metadata(cls, enabled: bool):
        if not enabled or getattr(args, "disable_metadata", False):
            return {}
        metadata = dict(cls.hidden.extra_pnginfo or {})
        if cls.hidden.prompt is not None:
            metadata["prompt"] = cls.hidden.prompt
        return metadata

    @staticmethod
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

    @staticmethod
    def _preview_ui(file, subfolder, folder_type, format_name, frame_rate, output_path):
        # VHS uses a ``gifs`` payload and renders the preview itself.  Keeping the
        # same payload lets the companion JS auto-play muted video on completion.
        return {
            "gifs": [{
                "filename": file,
                "subfolder": subfolder,
                "type": folder_type.value,
                "format": format_name,
                "frame_rate": frame_rate,
                "fullpath": output_path,
            }]
        }

    @classmethod
    def _save_animated_image(cls, frames, frame_rate, loop_count, full_output_folder, filename, counter, format_name, values):
        extension = format_name.split("/", 1)[1]
        file = f"{filename}_{counter:05}.{extension}"
        output_path = os.path.join(full_output_folder, file)
        images = [Image.fromarray(torch.frombuffer(bytearray(_to_uint8_bytes(frame)), dtype=torch.uint8).reshape(frame.shape).numpy()) for frame in frames]
        image_kwargs = {"duration": round(1000 / float(frame_rate)), "loop": int(loop_count), "save_all": True, "append_images": images[1:]}
        if extension == "gif":
            image_kwargs["disposal"] = 2
        else:
            image_kwargs["lossless"] = bool(values.get("lossless", True))
        images[0].save(output_path, format=extension.upper(), **image_kwargs)
        return file, output_path

    @classmethod
    def execute(
        cls,
        images: Input.Image,
        frame_rate: float,
        loop_count: int,
        filename_prefix: str,
        format: str,
        pingpong: bool,
        save_output: bool,
        audio: Optional[Input.Audio] = None,
        meta_batch=None,
        vae=None,
        **format_values,
    ) -> io.NodeOutput:
        if vae is not None and isinstance(images, dict) and "samples" in images:
            images = vae.decode(images["samples"])
        # Animated-image formats use Pillow's loop count.  Video formats repeat
        # frames in the encoded stream, as VHS's ffmpeg loop filter does.
        frames = cls._prepare_frames(images, pingpong, 0 if format in IMAGE_FORMATS else loop_count)
        if audio is not None and format_values.get("trim_to_audio", False):
            audio_seconds = audio["waveform"].shape[-1] / float(audio["sample_rate"])
            frames = frames[:max(1, min(len(frames), int(audio_seconds * float(frame_rate))))]
        elif audio is not None:
            wanted_samples = round(len(frames) * float(audio["sample_rate"]) / float(frame_rate))
            waveform = audio["waveform"]
            if waveform.shape[-1] < wanted_samples:
                audio = dict(audio)
                audio["waveform"] = torch.nn.functional.pad(waveform, (0, wanted_samples - waveform.shape[-1]))

        height, width = int(frames.shape[1]), int(frames.shape[2])
        output_dir = folder_paths.get_output_directory() if save_output else folder_paths.get_temp_directory()
        filename_prefix = _expand_vhs_date_prefix(filename_prefix)
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, output_dir, width, height)
        folder_type = io.FolderType.output if save_output else io.FolderType.temp

        if format in IMAGE_FORMATS:
            file, output_path = cls._save_animated_image(frames, frame_rate, loop_count, full_output_folder, filename, counter, format, format_values)
            return io.NodeOutput(
                InputImpl.VideoFromFile(output_path),
                ui=cls._preview_ui(file, subfolder, folder_type, format, frame_rate, output_path),
            )

        preset_name = format.removeprefix("video/")
        format_values["has_alpha"] = frames.shape[-1] == 4
        video_format = _apply_format_widgets(preset_name, format_values)
        dim_alignment = int(video_format.get("dim_alignment", 2))
        if width % dim_alignment or height % dim_alignment:
            pad_x, pad_y = -width % dim_alignment, -height % dim_alignment
            frames = torch.nn.functional.pad(
                frames.permute(0, 3, 1, 2).to(dtype=torch.float32),
                (pad_x // 2, pad_x - pad_x // 2, pad_y // 2, pad_y - pad_y // 2),
                mode="replicate",
            ).permute(0, 2, 3, 1)
            height, width = int(frames.shape[1]), int(frames.shape[2])
        extension = video_format["extension"]
        file = f"{filename}_{counter:05}.{extension}"
        output_path = os.path.join(full_output_folder, file)
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            raise ProcessLookupError("ffmpeg is required for Video Combine 🎥🅥🅗🅢 V2 outputs.")

        input_depth = video_format.get("input_color_depth", "8bit")
        if input_depth == "16bit":
            input_pix_fmt = "rgba64" if frames.shape[-1] == 4 else "rgb48"
            frame_bytes = b"".join(_to_uint16_bytes(frame) for frame in frames)
        else:
            input_pix_fmt = "rgba" if frames.shape[-1] == 4 else "rgb24"
            frame_bytes = b"".join(_to_uint8_bytes(frame) for frame in frames)

        command = [ffmpeg, "-v", "error", "-f", "rawvideo", "-pix_fmt", input_pix_fmt,
                   "-color_range", "pc", "-colorspace", "rgb", "-color_primaries", "bt709",
                   "-color_trc", video_format.get("fake_trc", "iec61966-2-1"), "-s", f"{width}x{height}",
                   "-r", str(frame_rate), "-i", "-"]
        temporary_paths = []
        metadata = cls._metadata(str(video_format.get("save_metadata", "True")) != "False")
        if audio is not None:
            audio_path = os.path.join(folder_paths.get_temp_directory(), f"feihou-vhs-audio-{uuid.uuid4().hex}.f32")
            waveform = audio["waveform"].squeeze(0).transpose(0, 1).detach().cpu().to(torch.float32).numpy()
            with open(audio_path, "wb") as stream:
                stream.write(waveform.tobytes())
            temporary_paths.append(audio_path)
            command += ["-f", "f32le", "-ar", str(audio["sample_rate"]), "-ac", str(waveform.shape[1]), "-i", audio_path]
        if metadata:
            metadata_path = os.path.join(folder_paths.get_temp_directory(), f"feihou-vhs-metadata-{uuid.uuid4().hex}.txt")
            cls._write_ffmetadata(metadata, metadata_path)
            temporary_paths.append(metadata_path)
            command += ["-i", metadata_path]
        # These are output options, so they must be placed after every input.
        if audio is not None:
            command += ["-map", "0:v:0", "-map", "1:a:0"]
        if metadata:
            command += ["-map_metadata", "2" if audio is not None else "1"]

        command += video_format["main_pass"]
        if video_format.get("bitrate") is not None:
            suffix = "M" if str(video_format.get("megabit")) == "True" else "K"
            command += ["-b:v", f"{video_format['bitrate']}{suffix}"]
        if audio is not None:
            command += video_format.get("audio_pass", ["-c:a", "libopus"])
            command += ["-shortest"]
        command += ["-metadata", "creation_time=now", "-movflags", "use_metadata_tags", output_path]
        _merge_filter_args(command)

        environment = os.environ.copy()
        environment.update(video_format.get("environment", {}))
        try:
            completed = subprocess.run(command, input=frame_bytes, env=environment, capture_output=True, check=False)
        finally:
            for temporary_path in temporary_paths:
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass
        if completed.returncode != 0:
            raise RuntimeError("ffmpeg could not save the selected VHS format:\n" + completed.stderr.decode("utf-8", errors="replace"))

        return io.NodeOutput(
            InputImpl.VideoFromFile(output_path),
            ui=cls._preview_ui(file, subfolder, folder_type, format, frame_rate, output_path),
        )
