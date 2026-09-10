"""Run with ComfyUI on PYTHONPATH and its Python environment; no network calls."""
import importlib
import json
import sys
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import torch
from PIL import Image

root = Path(__file__).resolve().parents[1]
package = types.ModuleType("fh_media_test")
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
media = importlib.import_module("fh_media_test.feihou_api_media")
nodes = importlib.import_module("fh_media_test.feihou_api_nodes")


class MediaTests(unittest.TestCase):
    def test_last_frame_output(self):
        import av
        import numpy as np
        data = BytesIO()
        with av.open(data, mode="w", format="mp4") as container:
            stream = container.add_stream("libx264", rate=8)
            stream.width = 16
            stream.height = 16
            stream.pix_fmt = "yuv420p"
            for level in (0, 120, 240):
                frame = av.VideoFrame.from_ndarray(np.full((16, 16, 3), level, dtype=np.uint8), format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        video = data.getvalue()
        tail = nodes._video_last_frame({}, video)
        self.assertEqual(tuple(tail.shape), (1, 16, 16, 3))
        self.assertGreater(float(tail.mean()), 0.9)
        image = BytesIO()
        Image.new("RGB", (8, 8), "red").save(image, format="PNG")
        with patch.object(nodes, "_download_bytes", return_value=image.getvalue()) as download:
            tail = nodes._video_last_frame({"content": {"last_frame_url": "https://example.com/tail.png"}}, video)
            self.assertEqual(tuple(tail.shape), (1, 8, 8, 3))
            download.assert_called_once()
        with patch.object(nodes, "_download_bytes", side_effect=ValueError("expired")):
            self.assertGreater(float(nodes._video_last_frame({"last_frame_url": "https://example.com/tail.png"}, video).mean()), 0.9)
        self.assertEqual(len(nodes.FeiHouApiVideo.define_schema().outputs), 3)

    def test_loader_bundle_and_audio_trim(self):
        import wave
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "audio.wav")
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(8000)
                writer.writeframes(b"\0\0" * 16000)
            data = json.dumps([{"media_type":"audio", "ordinal":2, "filename":"audio.wav", "audio_trim":"00:00.5-00:01"}])
            with patch.object(media.folder_paths,"get_input_directory",return_value=directory):
                output = media.FeiHouApiMediaLoader.execute(data)
                items = media.collect_media("[]", output.result[0])
                self.assertEqual(items[0][1],2)
                self.assertEqual(len(media.FeiHouApiMediaLoader.fingerprint_inputs(data)),1)
            with wave.open(BytesIO(media.media_bytes("audio",items[0][3])), "rb") as reader:
                self.assertEqual(reader.getnframes(),4000)
                self.assertEqual(reader.getframerate(),8000)

    def test_full_gallery_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            records = []
            for kind, count in media.LIMITS.items():
                filename = {"image":"ref.png", "video":"ref.mp4", "audio":"ref.wav"}[kind]
                Path(directory, filename).write_bytes(b"mock upload content")
                records.extend({"media_type":kind,"ordinal":i,"filename":filename} for i in range(1,count+1))
            with patch.object(media.folder_paths,"get_input_directory",return_value=directory):
                items = media.collect_media(json.dumps(records))
            body = {}
            uploads = []
            def upload(name, data, mime):
                uploads.append(name)
                return f"https://example.test/{len(uploads)}"
            media.prepare_media(body,"@image9 follows @video3 and @audio3", "seedance-2.0-standard-multi", "video",items,upload)
            self.assertEqual(len(uploads),15)
            self.assertEqual(len(body["metadata"]["content"]),15)
            self.assertEqual(body["prompt"],"@Image 9 follows @Video 3 and @Audio 3")
            self.assertNotIn("images",body)

    def test_references_and_unsupported_media_fail_before_upload(self):
        items = [("image",3,"ref.png",torch.zeros(4,4,3))]
        uploads=[]
        body={}
        media.prepare_media(body,"@图片3", "feihou-image-nb-2","image",items,lambda *a:uploads.append(a) or "https://example.test/i")
        self.assertEqual(body["prompt"],"图片1")
        uploads.clear()
        with self.assertRaises(ValueError):
            media.prepare_media({},"@image1","feihou-image-nb-2","image",items,lambda *a:uploads.append(a))
        with self.assertRaises(ValueError):
            media.prepare_media({},"test","feihou-image-nb-2","image",[("audio",1,"a.wav",{})],lambda *a:uploads.append(a))
        self.assertEqual(uploads,[])

    def test_native_inputs_and_limits(self):
        items=media.collect_media("[]",[torch.zeros(9,4,4,3),{"waveform":torch.zeros(1,1,800),"sample_rate":8000}])
        self.assertEqual(len(items),10)
        self.assertEqual(Image.open(BytesIO(media.media_bytes("image",items[0][3]))).size,(4,4))
        self.assertTrue(media.media_bytes("audio",items[-1][3]).startswith(b"RIFF"))
        with self.assertRaises(ValueError):media.collect_media("[]",torch.zeros(10,4,4,3))

    def test_storage_boundary_and_schemas(self):
        with self.assertRaises(ValueError):media.read_media_records('[{"media_type":"image","ordinal":1,"filename":"../../outside.png"}]')
        for cls,title in [(nodes.FeiHouApiImage,"FeiHou-API Images"),(nodes.FeiHouApiVideo,"FeiHou-API Video")]:
            schema=cls.define_schema()
            self.assertEqual(schema.display_name,title)
            self.assertIn("media",[item.id for item in schema.inputs])
            self.assertIn("media_files",[item.id for item in schema.inputs])


if __name__ == "__main__":unittest.main()
