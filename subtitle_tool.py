#!/usr/bin/env python3
"""
subtitle_tool.py — 跨平台视频字幕工具
支持 Windows / macOS / Linux
依赖: faster-whisper, ffmpeg（需在 PATH 中）

安装:
  pip install faster-whisper

用法:
  python subtitle_tool.py                        # 交互模式
  python subtitle_tool.py video.mp4              # 自动生成+嵌入字幕
  python subtitle_tool.py video.mp4 --srt x.srt # 使用已有字幕
  python subtitle_tool.py --batch                # 批量处理当前目录
"""

import argparse
import glob
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────
#  颜色输出（Windows 兼容）
# ─────────────────────────────────────────────
if platform.system() == "Windows":
    os.system("color")

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def info(msg):  print(f"{CYAN}[INFO]{RESET}  {msg}")
def ok(msg):    print(f"{GREEN}[OK]{RESET}    {msg}")
def warn(msg):  print(f"{YELLOW}[WARN]{RESET}  {msg}")
def error(msg): print(f"{RED}[ERROR]{RESET} {msg}")
def title(msg): print(f"\n{BOLD}{msg}{RESET}\n{'─'*50}")


# ─────────────────────────────────────────────
#  环境检查
# ─────────────────────────────────────────────
def check_deps():
    missing = []

    if not shutil.which("ffmpeg"):
        # PyInstaller 打包时 ffmpeg.exe 在 exe 同目录
        exe_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
        bundled = exe_dir / "ffmpeg.exe"
        if bundled.exists():
            os.environ["PATH"] = str(exe_dir) + os.pathsep + os.environ.get("PATH", "")
        else:
            missing.append("ffmpeg  →  https://ffmpeg.org/download.html")

    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        missing.append("faster-whisper  →  pip install faster-whisper")

    if missing:
        error("缺少以下依赖，请先安装：")
        for m in missing:
            print(f"  • {m}")
        sys.exit(1)

    ok("ffmpeg 和 faster-whisper 均已就绪")


# ─────────────────────────────────────────────
#  faster-whisper 生成字幕
#
#  模型下载体积（比 openai-whisper 小 ~4 倍）：
#    tiny   ~  39 MB   最快
#    base   ~  74 MB   较快
#    small  ~ 244 MB   均衡  ← 默认
#    medium ~ 769 MB   精准
#    large  ~1550 MB   最准
# ─────────────────────────────────────────────
def generate_srt(video_path: Path, model: str, language: str) -> Path:
    title(f"🎙 转录：{video_path.name}")

    from faster_whisper import WhisperModel

    # 自动选择设备
    try:
        import torch
        device  = "cuda" if torch.cuda.is_available() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
    except ImportError:
        device, compute = "cpu", "int8"

    info(f"加载模型：{model}  设备：{device}  精度：{compute}")
    info("首次使用会自动下载（模型体积约为 openai-whisper 的 1/4）...")

    m = WhisperModel(model, device=device, compute_type=compute)

    info(f"开始转录，语言：{language} ...")
    segments, meta = m.transcribe(
        str(video_path),
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    # 边转录边写入，实时显示进度
    srt_path = video_path.with_suffix(".srt")
    duration  = meta.duration or 1
    seg_list  = []

    print(f"  {'─'*48}")
    for seg in segments:
        seg_list.append(seg)
        pct = min(seg.end / duration * 100, 100)
        bar = "█" * int(pct / 4) + "░" * (25 - int(pct / 4))
        print(f"\r  [{bar}] {pct:5.1f}%  {seg.end:.0f}s / {duration:.0f}s",
              end="", flush=True)
    print()

    _write_srt(seg_list, srt_path)
    ok(f"字幕已保存：{srt_path}  （共 {len(seg_list)} 段）")
    return srt_path


def _write_srt(segments, path: Path):
    def fmt(t):
        h  = int(t // 3600)
        m  = int((t % 3600) // 60)
        s  = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt(seg.start)} --> {fmt(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")


# ─────────────────────────────────────────────
#  FFmpeg 嵌入字幕
# ─────────────────────────────────────────────
def embed_subtitle(
    video_path: Path,
    srt_path: Path,
    mode: str,
    font_name: str,
    font_size: int,
    output_path: Path | None = None,
) -> Path:
    title(f"🎬 嵌入字幕：{video_path.name}")

    suffix = video_path.suffix.lower()
    out = output_path or video_path.with_name(
        video_path.stem + "_subtitled" + suffix
    )

    if mode == "soft":
        sub_codec = "srt" if suffix == ".mkv" else "mov_text"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(srt_path),
            "-c", "copy",
            "-c:s", sub_codec,
            str(out),
        ]
    else:
        srt_str = _escape_srt_path(srt_path)
        style = (
            f"FontName={font_name},FontSize={font_size},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles={srt_str}:force_style='{style}'",
            "-c:a", "copy",
            str(out),
        ]

    info(f"模式：{'软字幕（可开关）' if mode == 'soft' else '硬字幕（烧录）'}")
    info(f"输出：{out}")

    ret = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if ret.returncode != 0:
        error("FFmpeg 出错：")
        for line in ret.stderr.strip().splitlines()[-15:]:
            print(f"  {line}")
        sys.exit(1)

    ok(f"完成 → {out}")
    return out


def _escape_srt_path(path: Path) -> str:
    s = str(path.resolve())
    if platform.system() == "Windows":
        s = s.replace("\\", "/")
        if len(s) >= 2 and s[1] == ":":
            s = s[0] + "\\:" + s[2:]
    s = s.replace("'", "\\'").replace(":", "\\:")
    return f"'{s}'"


# ─────────────────────────────────────────────
#  单文件处理
# ─────────────────────────────────────────────
def process_one(video_path: Path, args):
    video_path = video_path.resolve()
    if not video_path.exists():
        error(f"文件不存在：{video_path}")
        return

    if args.srt:
        srt_path = Path(args.srt).resolve()
        if not srt_path.exists():
            error(f"字幕文件不存在：{srt_path}")
            return
        info(f"使用已有字幕：{srt_path.name}")
    else:
        srt_path = generate_srt(video_path, args.model, args.language)

    embed_subtitle(
        video_path=video_path,
        srt_path=srt_path,
        mode=args.mode,
        font_name=args.font,
        font_size=args.font_size,
        output_path=Path(args.output) if args.output else None,
    )


# ─────────────────────────────────────────────
#  目录选择
# ─────────────────────────────────────────────
def pick_video_from_dir(d: Path) -> Path | None:
    exts  = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
    files = sorted([f for f in d.iterdir() if f.suffix.lower() in exts])
    if not files:
        error(f"目录中没有找到视频文件：{d}")
        return None

    print(f"\n{BOLD}在 {d} 找到以下视频：{RESET}")
    for i, f in enumerate(files, 1):
        size_mb = f.stat().st_size / 1_048_576
        print(f"  {CYAN}{i:2d}{RESET}. {f.name}  {YELLOW}({size_mb:.0f} MB){RESET}")

    while True:
        choice = input(f"\n请输入编号（1-{len(files)}），或输入 0 退出：").strip()
        if choice == "0":
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(files):
            return files[int(choice) - 1]
        warn("请输入有效编号")


# ─────────────────────────────────────────────
#  交互模式
# ─────────────────────────────────────────────
def interactive_mode():
    title("🎬 视频字幕工具 — 交互模式")

    raw = input("请输入视频文件路径（或拖拽文件/目录到此处）：").strip().strip('"').strip("'")
    if not raw:
        error("未输入路径，退出")
        sys.exit(1)

    p = Path(raw)
    if p.is_dir():
        chosen = pick_video_from_dir(p)
        if chosen is None:
            sys.exit(0)
        video = str(chosen)
    elif p.is_file():
        video = str(p)
    else:
        error(f"路径不存在：{p}")
        sys.exit(1)

    print("\nWhisper 模型（faster-whisper，下载体积约为原版 1/4）：")
    print("  tiny=39MB最快  base=74MB  small=244MB均衡  medium=769MB  large=1.5GB最准")
    model = input("选择模型（直接回车=small）：").strip() or "small"

    print("\n字幕模式：soft（可开关）/ hard（烧录到画面）")
    mode = input("选择模式（直接回车=soft）：").strip() or "soft"

    class A:
        srt      = None
        language = "zh"
        output   = None
        batch    = False
        font     = "Microsoft YaHei" if platform.system() == "Windows" else "PingFang SC"
        font_size = 22

    a       = A()
    a.model = model
    a.mode  = mode
    process_one(Path(video), a)


# ─────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────
def build_parser():
    p = argparse.ArgumentParser(
        description="跨平台视频字幕工具（faster-whisper + FFmpeg）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("videos", nargs="*", help="视频文件路径（支持通配符）")
    p.add_argument("--srt",      help="使用已有 .srt，跳过转录")
    p.add_argument("--model",    default="small",
                   help="模型名称或本地路径（默认 small）")
    p.add_argument("--language", default="zh", help="转录语言（默认 Chinese）")
    p.add_argument("--mode",     default="soft", choices=["soft","hard"],
                   help="soft=软字幕  hard=硬字幕烧录（默认 soft）")
    p.add_argument("--font",     default="Microsoft YaHei")
    p.add_argument("--font-size",type=int, default=22, dest="font_size")
    p.add_argument("--output",   help="输出路径（单文件时有效）")
    p.add_argument("--batch",    action="store_true",
                   help="批量处理当前目录所有 mp4/mkv")
    return p


def main():
    check_deps()
    parser = build_parser()
    args   = parser.parse_args()

    if args.font == "Microsoft YaHei" and platform.system() == "Darwin":
        args.font = "PingFang SC"

    if not args.videos:
        interactive_mode()
        return

    video_files = []
    for pattern in args.videos:
        expanded = glob.glob(pattern)
        video_files.extend(expanded if expanded else [pattern])

    if args.batch:
        cwd = Path(".")
        video_files = list(cwd.glob("*.mp4")) + list(cwd.glob("*.mkv"))
        if not video_files:
            warn("当前目录没有找到 mp4/mkv 文件")
            return
        info(f"批量模式：找到 {len(video_files)} 个文件")

    for v in video_files:
        process_one(Path(v), args)

    title("✅ 全部完成！")


if __name__ == "__main__":
    main()