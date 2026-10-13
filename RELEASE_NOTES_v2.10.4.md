# FeiHou Toolbox v2.10.4

## 新增

- `Video Combine 🎥🅥🅗🅢 V2` 新增可选 `latent` 接口，连上后在视频旁边保存同名 `.latent` 文件（ComfyUI Save Latent 格式；视频与音频 latent 保存在同一个文件）。
- 配合 FeiHou Easy H3「接续合并」的 `tail_latent`：
  - 每段都保存 `.latent`（包括最后一段，便于以后延长）；Easy H3 加载器选「硬切」时不保存。
  - 每段的视频与 `.latent` 记录在 `output/feihou_h3_continuation/<制作包>.json`，重跑第 N 段会替换第 N 段及之后的记录；Easy H3 重启后或单独重跑时据此读取上一段的 `.latent` 接续。
  - 最后一段跑完后，把各段已保存的视频用 ffmpeg 无损拼接（不重新编码）成同目录的 `<最后一段文件名>_完整.mp4`，并显示在节点预览里。

## 兼容

- 不连接 `latent` 时，节点行为与 v2.10.3 完全相同；旧工作流无需修改。
