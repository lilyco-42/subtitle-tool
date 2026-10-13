# Lain42 字幕工坊（尚未发行）

原 `subtitle_tool.py` 的本机工作台，FastAPI + React/shadcn + Windows WebView2；不上传文件，不用付费 API。
视频进入个人电脑的临时目录，选择视频、生成或导入 SRT、校对与播放、导出软字幕或烧录字幕及成果 ZIP。
每组最多三个视频、每个 256 MB、总计 512 MB，按顺序处理以限制 CPU；每个视频独立校对字幕。
任务支持取消；清空会删除临时文件和有上限的历史，请先下载。原编码不被浏览器支持时会提示，仍可处理。

本目录复用原 CLI，不另造 ASR 或视频编码器。增加原 CLI 的 `--transcribe-only`、CPU/自动设备和本地模型/媒体选项，
使校对在烧录之前完成。桌面适配器固定执行自己的引擎、模型路径和输出，HTTP 不接受命令、可执行路径或任意磁盘路径。
loopback Host/Origin、端口独立 HttpOnly 会话与严格 CSP 保护本机接口；引擎在任务控制器接管后才开始处理，
Unix 独立进程组、Windows nested Job Object 只管理当前任务树。

## 验收边界

`Subtitle workbench` 在 Actions 构建实际 UI 并调用原 CLI，验证已有字幕的完整浏览器流程及 HTTP 隔离。
H264/AAC 的播放路径使用真实 Google Chrome 验收；当前无品牌 Chromium 明确不支持该编解码组合。
不支持的源格式仍显示提示，字幕生成与导出不依赖浏览器解码能力；不能据此声称所有浏览器都能播放所有视频。
没有本机构建或测试。CI 源码引擎入口仅在 `GITHUB_ACTIONS=true` 且 `LAIN42_SUBTITLE_SOURCE_ENGINE=true` 时启用；
产品必须提供已冻结的 `bin/subtitle-engine/`。模型缺失时不伪造转录能力。

**当前不能作为完整桌面产品发行或收费交付。** 剩余门：固定本地模型及文件/许可、真实语音识别、
FFmpeg 及原生依赖对应源码/许可、冻结后的原引擎、Windows 原生窗口/取消/正常退出及 EXE 安装/卸载。
所有门通过才在原仓库 Release 和 Lain42 提供可交付包；不能把这个源码工作台或绿色前端构建当作产品完成。

来源与许可见 `SOURCES.md`，设计约束见 `DESIGN.md`。
