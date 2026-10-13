# subtitle-tool

跨平台视频字幕工具 —— 基于 **faster-whisper** 语音识别 + FFmpeg 字幕嵌入。

Windows / macOS / Linux 均可使用。

## 功能

- 自动识别视频语音，生成 `.srt` 字幕
- 支持软字幕（可开关）和硬字幕（烧录到画面）
- 支持已有字幕直接嵌入，跳过转录
- 交互模式、命令行模式、批量处理
- 自动选择 CPU / CUDA

## 安装

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装 FFmpeg（如果 PATH 中没有）
#    Windows:  choco install ffmpeg  或  https://ffmpeg.org/download.html
#    macOS:    brew install ffmpeg
#    Linux:    apt install ffmpeg
```

## 用法

```bash
# 交互模式（拖拽视频即可）
python subtitle_tool.py

# 自动生成字幕并嵌入
python subtitle_tool.py video.mp4

# 使用已有字幕文件
python subtitle_tool.py video.mp4 --srt existing.srt

# 硬字幕（烧录到画面）
python subtitle_tool.py video.mp4 --mode hard

# 批量处理当前目录所有视频
python subtitle_tool.py --batch

# 指定模型（tiny/base/small/medium/large）
python subtitle_tool.py video.mp4 --model medium

# 使用本地下载好的模型
python subtitle_tool.py video.mp4 --model ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
```

## 软字幕 vs 硬字幕

| 模式 | 特点 | 适用场景 |
|------|------|----------|
| `soft` | 字幕作为独立轨道存入文件，播放器可开关 | VLC、PotPlayer、mpv 等播放器 |
| `hard` | 字幕直接烧录到画面，无法关闭 | 剪映/CapCut 等剪辑软件、浏览器、手机自带播放器 |

**注意**：剪映、CapCut、Premiere 等剪辑软件通常**不支持读取 MP4 的软字幕轨道**。如果需要导入剪辑软件，请使用 `--mode hard` 烧录字幕，或直接把生成的 `.srt` 文件拖入时间线。

## 模型选择

CLI 支持 tiny / base / small / medium / large 或本地转换模型。
大小取决于具体模型仓库、精度与版本，不能直接套用 OpenAI 原版权重的体积。
本次 Actions 实际取得的固定 Tiny 版本五个模型文件与完整许可合计 78,206,673 字节；
这不是完整桌面应用体积，也不是准确率或速度保证。其他模型尚未在桌面包验证。

faster-whisper 1.2.1 与 PyAV 16.0.1 固定配套：真实 ASR 发现新 PyAV 不再接受
`av.open(metadata_errors=...)`，不能仅通过前端构建或已有字幕测试判断转录可用。

首次使用会自动下载模型到 `~/.cache/huggingface/`。

## 直接下载 EXE

如果不想装 Python，可以从 [Releases](https://github.com/lilyco-42/subtitle-tool/releases) 下载打包好的 `subtitle_tool.exe`，解压后双击即可使用（已将 ffmpeg 打包在内）。

## License

MIT

## 桌面封装准备与回归

字幕工作台源码位于 [`desktop/`](desktop/README.md)，包含视频预览、SRT 校对与逐个／批量导出。
目前是待验收实现，尚未发布完整桌面安装包；模型、媒体依赖、冻结与安装门必须全部通过才交付。

现有 CLI 的批量与嵌入行为由 `Subtitle CLI regression` 在 GitHub Actions 的 Windows / Linux 验证。
`--help` 不加载模型；使用 `--srt` 时不需要安装或下载语音识别模型。`--batch` 不再进入交互提示，
排除已经生成的 `_subtitled` 视频；任意文件失败会以非零状态退出，不显示“全部完成”。
`--output` 只允许单文件处理，不能覆盖原视频或字幕。软字幕根据**输出**容器选择编码，
明确使用新字幕并保留音视频；支持 MP4 / MOV / MKV，其他输入的默认软字幕输出使用 MKV。
硬字幕使用临时字幕副本，支持含空格、中文及引号的原字幕路径。

这些是原 CLI 的前置修补，**不是已发布的 GUI 产品**。后续桌面版仍需要完成字幕编辑／预览、
原引擎转录、批量导出、取消，以及模型、FFmpeg 和 WebView 的完整打包许可与安装验收。
所有产品构建与测试只在 GitHub Actions；本机不编译、冻结或运行产品测试。
