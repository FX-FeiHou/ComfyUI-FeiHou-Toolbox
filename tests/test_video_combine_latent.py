"""Run with the ComfyUI Python environment and ComfyUI on PYTHONPATH."""
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from safetensors import safe_open

root = Path(__file__).resolve().parents[1]
package = types.ModuleType("fh_video_test")
package.__path__ = [str(root)]
sys.modules[package.__name__] = package

# Route decorators need an instance when importing outside a running server.
import server


class Routes:
    def get(self, *args, **kwargs):
        return lambda handler: handler


with patch.object(server.PromptServer, "instance", types.SimpleNamespace(
        routes=Routes(), prompt_queue=types.SimpleNamespace(currently_running={})), create=True):
    video = importlib.import_module("fh_video_test.video_combine_v2")

if "--cpu" in sys.argv:
    sys.argv.remove("--cpu")


class LatentSaveTests(unittest.TestCase):
    def test_frame_rate_schema_keeps_widget_and_socket(self):
        schema = video.VideoCombineV2.define_schema()
        fps = next(item for item in schema.inputs if item.id == "frame_rate")
        self.assertFalse(fps.socketless)
        self.assertTrue(fps.optional)
        self.assertEqual(fps.default, 8.0)

    def test_tensor_and_metadata_roundtrip(self):
        samples = torch.arange(8, dtype=torch.float32).reshape(1, 2, 2, 2)
        audio = torch.ones(1, 2, 3)
        latent = {"samples": samples, "feihou_save": {
            "tensors": {"audio_latent": audio}, "metadata": {"segment": 2}}}
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "clip.latent")
            self.assertEqual(video._save_latent(target, latent, {"workflow": {"nodes": []}}), target)
            with safe_open(target, framework="pt") as saved:
                self.assertTrue(torch.equal(saved.get_tensor("latent_tensor"), samples))
                self.assertTrue(torch.equal(saved.get_tensor("audio_latent"), audio))
                self.assertIn("latent_format_version_0", saved.keys())
                self.assertEqual(json.loads(saved.metadata()["workflow"]), {"nodes": []})
                self.assertEqual(saved.metadata()["segment"], "2")
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["clip.latent"])

    def test_empty_latent_creates_no_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "empty.latent"
            self.assertIsNone(video._save_latent(str(target), {}, {}))
            self.assertFalse(target.exists())

    def test_nested_tensor_parts(self):
        parts = [torch.ones(1), torch.zeros(2)]
        result = video._latent_tensors({"samples": types.SimpleNamespace(tensors=parts)})
        self.assertEqual(set(result), {"latent_tensor", "latent_tensor_1"})
        self.assertTrue(torch.equal(result["latent_tensor_1"], parts[1]))

    def test_manifest_rerun_discards_later_segments(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = str(Path(folder) / "series.json")
            video._write_manifest(manifest, {"shots": {
                "1": {"video": "first.mp4"}, "2": {"video": "old.mp4"}, "3": {"video": "later.mp4"}}})
            latent = {"feihou_save": {"manifest": manifest, "index": 2, "total": 3, "save_latent": False}}
            self.assertIsNone(video.VideoCombineV2._save_series("new.mp4", latent, {}))
            saved = video._read_manifest(manifest)
            self.assertEqual(set(saved["shots"]), {"1", "2"})
            self.assertEqual(saved["shots"]["2"]["video"], "new.mp4")

    def test_real_ffmpeg_concat(self):
        import av
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for index in range(2):
                target = str(Path(folder) / f"segment{index}.mp4")
                with av.open(target, mode="w", format="mp4") as container:
                    stream = container.add_stream("libx264", rate=8)
                    stream.width = stream.height = 16
                    stream.pix_fmt = "yuv420p"
                    for frame_index in range(3):
                        frame = av.VideoFrame.from_ndarray(np.full((16, 16, 3), index * 120, dtype=np.uint8), format="rgb24")
                        for packet in stream.encode(frame):
                            container.mux(packet)
                    for packet in stream.encode():
                        container.mux(packet)
                paths.append(target)
            target = str(Path(folder) / "joined.mp4")
            self.assertEqual(video._concat_videos(paths, target), target)
            with av.open(target) as container:
                self.assertEqual(len(list(container.decode(video=0))), 6)
            self.assertEqual(len(list(Path(folder).iterdir())), 3)


if __name__ == "__main__":
    unittest.main()
