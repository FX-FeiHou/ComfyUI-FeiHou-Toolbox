# v2.10.0 · FeiHou API 多媒体生成

## 花果山Ai灵境坊

- 网站 / API 服务：[api.fei-hou.net](https://api.fei-hou.net/)
- Windows 客户端下载：[GitHub](https://github.com/FX-FeiHou/FeiHou-Ai-Studio/releases/latest) · [夸克网盘](https://pan.quark.cn/s/327190b9484c)。首次使用请选择 `FeiHou-Ai-Studio-Win-1.1.4-full.zip` 完整包；已有用户优先通过启动器更新。GitHub 自动生成的 Source code 不是客户端安装包。

## 更新说明

- 新增 **FeiHou-API Images** 和 **FeiHou-API Video**：填写 API Key、刷新模型列表并选择模型，在 ComfyUI 内调用花果山Ai灵境坊 API 生图、生视频。
- 按模型显示分辨率、画面比例、时长、种子、音频生成等适用参数；扩充模型列表发现来源。
- 新增独立 **FeiHou-API Media**：支持最多 9 张图片、3 个视频、3 个音频，支持替换、删除、同类拖动排序和音频截取。实际可提交媒体类型与数量仍受所选模型限制。
- 原生提示词输入框支持通过 `@` 选择已连接的媒体；保留媒体记录的复制和工作流序列化。
- API Video 输出原生 VIDEO、视频链接及尾帧 IMAGE。优先采用 API 返回的尾帧图片；未返回或下载失败时从视频提取最后一帧，不额外保存 PNG。原生 VIDEO 保留返回文件已有的音轨，不另设 AUDIO 输出。
- 修正媒体区边距、动态卡片布局、底部缩放、隐藏记录重叠与旧参考图输入迁移，补充中英 i18n。
- 使用作者更新后的生图 / 视频合并范例工作流，保留其布局、连线与参数。

## 使用提示

- 更新后重启 ComfyUI，并强制刷新浏览器前端。
- 范例：`workflows/FeiHou_API_Image&Video_example.json`。其中的文本显示与分组开关需要 ComfyUI-Custom-Scripts 和 rgthree-comfy，API 节点自身不依赖它们。
- 分享工作流前清除 API Key。工作流 JSON 不包含本地素材文件，迁移到其他机器后需重新上传素材。
- 尚未在 RunningHub 平台完成实测，不承诺其应用页面保留自定义媒体与 `@` 界面。

## 验证

6 项离线后端测试、媒体 UI 测试、JavaScript 语法与 JSON 校验通过。未调用付费 API 执行在线生成测试。
