# FeiHou Toolbox v2.10.3

## 修复

- 修复新版 ComfyUI 前端载入旧工作流时，`Video Combine 🎥🅥🅗🅢 V2` 节点的 `frame_rate` 控件可能消失的问题。
- 当旧节点没有序列化帧率控件时，前端会自动补回 `frame_rate`，并从命名字段或旧版位置数组恢复保存值。
- 保持后端默认帧率 8 FPS、已连接输入优先级和原有 Video Helper Suite 控件顺序不变。
