"""Temporary VideoHelperSuite-compatible preview output for FeiHou Toolbox."""

import copy

from comfy_api.latest import io

from .vhs_compat.nodes import VideoCombine as _VHSVideoCombine


class FeiHouVideoPreview(io.ComfyNode):
    """Encode an IMAGE batch only to ComfyUI's temporary preview directory."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="FeiHouVideoPreview",
            # English remains the server-side fallback.  The frontend supplies
            # the Chinese title when the ComfyUI locale is Chinese.
            display_name="FeiHou-Video Preview",
            category="FeiHou Toolbox/video",
            description="Preview an image batch as H.264 video without saving an output file.",
            search_aliases=["FeiHou-视频预览", "FeiHou video preview", "video preview", "视频预览"],
            inputs=[
                io.Image.Input("images"),
                io.Audio.Input("audio", optional=True),
                io.Float.Input(
                    "frame_rate",
                    default=8.0,
                    min=1.0,
                    step=1.0,
                    optional=True,
                    socketless=True,
                ),
            ],
            outputs=[],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo, io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images, audio=None, frame_rate=8.0) -> io.NodeOutput:
        # VideoHelperSuite writes previews to ComfyUI's temp directory when
        # save_output is false.  Disable its metadata PNG and silent-video
        # intermediate retention so this node never creates an output save.
        original_extra = cls.hidden.extra_pnginfo or {}
        extra_pnginfo = copy.deepcopy(original_extra)
        workflow = extra_pnginfo.setdefault("workflow", {})
        workflow.setdefault("extra", {})["VHS_MetadataImage"] = False
        workflow["extra"]["VHS_KeepIntermediate"] = False

        result = _VHSVideoCombine().combine_video(
            images=images,
            frame_rate=float(frame_rate),
            loop_count=0,
            filename_prefix="feihou_preview",
            format="video/h264-mp4",
            pingpong=False,
            save_output=False,
            prompt=None,
            extra_pnginfo=extra_pnginfo,
            audio=audio,
            unique_id=cls.hidden.unique_id,
            meta_batch=None,
            vae=None,
            pix_fmt="yuv420p",
            crf=19,
            save_metadata=False,
            trim_to_audio=False,
        )
        return io.NodeOutput(ui=result.get("ui", {}))
