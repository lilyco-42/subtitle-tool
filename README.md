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

## 模型选择

| 模型 | 大小 | 速度 | 精度 |
|------|------|------|------|
| tiny | ~39 MB | 最快 | 一般 |
| base | ~74 MB | 较快 | 尚可 |
| **small** | **~244 MB** | **均衡** | **推荐** |
| medium | ~769 MB | 较慢 | 精准 |
| large | ~1.5 GB | 最慢 | 最准 |

首次使用会自动下载模型到 `~/.cache/huggingface/`。

## 直接下载 EXE

如果不想装 Python，可以从 [Releases](https://github.com/your/repo/releases) 下载打包好的 `subtitle_tool.exe`，解压后双击即可使用（已将 ffmpeg 打包在内）。

## License

MIT
