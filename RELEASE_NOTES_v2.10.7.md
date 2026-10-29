# FeiHou Toolbox v2.10.7

## 修复

- 修复 `Video Combine 🎥🅥🅗🅢 V2` 的 `crf`、`pix_fmt` 等格式参数不生效的问题：之前这些参数被 ComfyUI 丢弃，始终按默认值（h264 为 crf 19）编码，现在修改 `crf` 会正常改变压缩率。需要 2026 年 1 月之后的 ComfyUI；更老的版本节点仍可使用，但会在日志中提示这些参数保持默认值。
- 修复与 VideoHelperSuite 的冲突：V2 前端注册的数字控件与 VHS 同名（`VHSFLOAT`/`VHSINT`），加载顺序靠后时会替换 Load Video、Video Combine 等所有 VHS 节点的控件。现改用 FeiHou 独立名称，两个插件互不影响。
- V2 连接 VHS 的 Meta Batch Manager 时，现在可以正常自动排队后续批次。

节点注册键、输入输出和旧工作流均保持兼容。

## 更新

通过 Manager 或 `git pull` 更新，或下载 Release 完整 ZIP。此版本同时修改了后端和前端，更新后需要重启 ComfyUI 并强制刷新浏览器。

花果山Ai灵境坊：https://api.fei-hou.net/

客户端下载：[GitHub](https://github.com/FX-FeiHou/FeiHou-Ai-Studio/releases/latest) · [夸克网盘](https://pan.quark.cn/s/327190b9484c)
