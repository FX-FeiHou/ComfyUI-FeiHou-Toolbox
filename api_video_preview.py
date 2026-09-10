"""Native VIDEO previews compatible with ComfyUI 0.33.1 and newer."""

import os
import uuid

import folder_paths
from comfy_api.latest import Types, io, ui


def save_video_preview(video):
    # Do not import comfy_extras.nodes_video helpers: older ComfyUI releases
    # lack save_video_preview, which would prevent the whole toolbox loading.
    filename = f"feihou_api_preview_{uuid.uuid4().hex}.mp4"
    directory = folder_paths.get_temp_directory()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    try:
        # The older save_to API does not accept the newer preset keyword.
        video.save_to(path, format=Types.VideoContainer.MP4, codec=Types.VideoCodec.AUTO)
    except Exception:
        if os.path.isfile(path):
            os.remove(path)
        raise
    return ui.PreviewVideo([ui.SavedResult(filename, "", io.FolderType.temp)])
