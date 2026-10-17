# FeiHou Toolbox v2.10.5

## 修复

- `Video Combine 🎥🅥🅗🅢 V2` 的帧率同时保留数值栏和外接输入接口，支持 FLOAT 和 INT。
- 修复此前 `socketless=True` 导致新建节点没有帧率接口的问题。
- 旧版工作流缺失的帧率数值栏或接口会自动恢复；已有接口的位置、连线和帧率值保持不变，继续兼容旧版数组格式与按名称保存的数据。
- 不修改节点注册键、输入字段名和其他节点，不影响视频预览、视频格式、单文件音频合并、工作流元数据、无首帧 PNG 及 latent/接续功能。

## 更新

通过 Manager 或 `git pull` 更新，或下载 Release 完整 ZIP。重启 ComfyUI 并强制刷新浏览器，使后端定义和前端扩展同时生效；无需重建旧工作流节点。

花果山Ai灵境坊：https://api.fei-hou.net/

客户端下载：[GitHub](https://github.com/FX-FeiHou/FeiHou-Ai-Studio/releases/latest) · [夸克网盘](https://pan.quark.cn/s/327190b9484c)
