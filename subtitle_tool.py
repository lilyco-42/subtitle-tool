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
import tempfile
from pathlib import Path

# ─────────────────────────────────────────────
#  颜色输出（Windows 兼容）
# ─────────────────────────────────────────────
if platform.system() == "Windows":
    os.system("color")
    # 桌面壳与重定向日志使用管道；Windows 默认 cp1252 无法输出中文/emoji。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def info(msg):  print(f"{CYAN}[INFO]{RESET}  {msg}", flush=True)
def ok(msg):    print(f"{GREEN}[OK]{RESET}    {msg}", flush=True)
def warn(msg):  print(f"{YELLOW}[WARN]{RESET}  {msg}", flush=True)
def error(msg): print(f"{RED}[ERROR]{RESET} {msg}", flush=True)
def title(msg): print(f"\n{BOLD}{msg}{RESET}\n{'─'*50}", flush=True)


# ─────────────────────────────────────────────
#  环境检查
# ─────────────────────────────────────────────
def check_deps(require_asr=True):
    missing = []

    if not shutil.which("ffmpeg"):
        # onefile 解包目录与 EXE 所在目录不同；两种布局都支持。
        exe_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
        roots = [Path(getattr(sys, '_MEIPASS', exe_dir)), exe_dir]
        executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        bundled_dir = next((root for root in roots if (root / executable).is_file()), None)
        if bundled_dir is None:
            missing.append("ffmpeg  →  https://ffmpeg.org/download.html")
        else:
            os.environ["PATH"] = str(bundled_dir) + os.pathsep + os.environ.get("PATH", "")

    if require_asr:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            missing.append("faster-whisper  →  pip install faster-whisper")

    if missing:
        error("缺少以下依赖，请先安装：")
        for m in missing:
            print(f"  • {m}")
        sys.exit(1)

    ok("ffmpeg 和 faster-whisper 均已就绪" if require_asr else "ffmpeg 已就绪（使用已有字幕）")


# ─────────────────────────────────────────────
#  faster-whisper 生成字幕
#
#  下载体积取决于模型仓库、转换精度与版本，不套用原版权重大小。
# ─────────────────────────────────────────────
def generate_srt(video_path: Path, model: str, language: str,
                 output_path: Path | None = None, device: str = "auto",
                 local_only: bool = False) -> Path:
    title(f"🎙 转录：{video_path.name}")

    from faster_whisper import WhisperModel

    # 自动选择设备
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    compute = "float16" if device == "cuda" else "int8"

    info(f"加载模型：{model}  设备：{device}  精度：{compute}")
    info("使用本地模型，不发起模型下载" if local_only else "模型不存在时会下载，请保持网络连接")

    m = WhisperModel(model, device=device, compute_type=compute, local_files_only=local_only)

    info(f"开始转录，语言：{language} ...")
    srt_path = output_path or video_path.with_suffix(".srt")
    if srt_path.resolve() == video_path.resolve():
        raise ValueError("字幕输出不能覆盖输入视频")
    seg_list  = []
    with tempfile.TemporaryDirectory(prefix="subtitle-audio-", dir=srt_path.resolve().parent) as directory:
        media = video_path
        if local_only:
            # PyAV 的自动格式识别也可能识别播放列表。先由受协议白名单
            # 限制的 FFmpeg 生成已知 PCM，识别器只读取这份本地音频。
            media = Path(directory) / "audio.wav"
            ret = subprocess.run(["ffmpeg", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
                                  "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000",
                                  "-c:a", "pcm_s16le", str(media)], capture_output=True)
            if ret.returncode:
                raise RuntimeError("无法安全读取本地音频：" + ret.stderr.decode("utf-8", errors="replace")[-2000:])
        segments, meta = m.transcribe(
            str(media), language=None if language == "auto" else language, beam_size=5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
        )
        duration = meta.duration or 1
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
    local_only: bool = False,
) -> Path:
    title(f"🎬 嵌入字幕：{video_path.name}")

    video_path = video_path.resolve()
    srt_path = srt_path.resolve()
    suffix = video_path.suffix.lower()
    if mode == "soft" and suffix not in {".mp4", ".mov", ".mkv"}:
        suffix = ".mkv"
    out = output_path or video_path.with_name(
        video_path.stem + "_subtitled" + suffix
    )
    out = out.resolve()
    if out in {video_path, srt_path}:
        raise ValueError("输出路径不能覆盖输入视频或字幕")
    if mode not in {"soft", "hard"}:
        raise ValueError("字幕模式必须为 soft 或 hard")
    if not isinstance(font_size, int) or font_size < 1:
        raise ValueError("字幕字号必须是正整数")
    if any(char in font_name for char in "'\\,:;[]\r\n"):
        raise ValueError("字体名称含不支持的控制字符")

    if mode == "soft":
        output_suffix = out.suffix.lower()
        if output_suffix not in {".mkv", ".mp4", ".mov"}:
            raise ValueError("软字幕输出请选择 .mkv、.mp4 或 .mov；其他格式请使用硬字幕")
        sub_codec = "srt" if output_suffix == ".mkv" else "mov_text"
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-i", str(video_path),
            "-i", str(srt_path),
            "-map", "0:v:0", "-map", "0:a?", "-map", "1:s:0",
            "-c", "copy",
            "-c:s", sub_codec,
            str(out),
        ]
    else:
        style = (
            f"FontName={font_name},FontSize={font_size},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2"
        )
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-i", str(video_path),
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", f"subtitles=subtitle.srt:force_style='{style}'",
            "-c:a", "copy",
            str(out),
        ]

    if local_only:
        # 设置在每个输入前，拒绝伪装为本地视频的远程播放列表。
        for index in reversed([i for i, item in enumerate(cmd) if item == "-i"]):
            cmd[index:index] = ["-protocol_whitelist", "file,pipe"]

    info(f"模式：{'软字幕（可开关）' if mode == 'soft' else '硬字幕（烧录）'}")
    info(f"输出：{out}")

    # 固定滤镜内的文件名，避免 Windows 盘符、引号、冒号的多层转义。
    # 输入和输出仍使用绝对路径，临时目录只持有本次字幕副本。
    with tempfile.TemporaryDirectory(prefix="subtitle-filter-", dir=out.parent) as directory:
        if mode == "hard":
            shutil.copyfile(srt_path, Path(directory) / "subtitle.srt")
        ret = subprocess.run(cmd, cwd=directory, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace")
    if ret.returncode != 0:
        raise RuntimeError("FFmpeg 出错：\n" + "\n".join(ret.stderr.strip().splitlines()[-15:]))
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("FFmpeg 未生成有效输出文件")

    ok(f"完成 → {out}")
    return out


# ─────────────────────────────────────────────
#  单文件处理
# ─────────────────────────────────────────────
def process_one(video_path: Path, args):
    video_path = video_path.resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"文件不存在：{video_path}")

    if args.srt:
        srt_path = Path(args.srt).resolve()
        if not srt_path.is_file():
            raise FileNotFoundError(f"字幕文件不存在：{srt_path}")
        info(f"使用已有字幕：{srt_path.name}")
    else:
        srt_path = generate_srt(video_path, args.model, args.language,
                               output_path=Path(args.output) if args.transcribe_only and args.output else None,
                               device=args.device, local_only=args.local_only)
    if args.transcribe_only:
        return srt_path

    return embed_subtitle(
        video_path=video_path,
        srt_path=srt_path,
        mode=args.mode,
        font_name=args.font,
        font_size=args.font_size,
        output_path=Path(args.output) if args.output else None,
        local_only=args.local_only,
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

    print("\nWhisper 模型（faster-whisper 转换版）：")
    print("  tiny / base / small / medium / large，下载体积以具体模型版本为准")
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
        transcribe_only = False
        device = "auto"
        local_only = False

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
    p.add_argument("--transcribe-only", action="store_true", help="只生成 SRT，预览修改后再嵌入")
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto", help="选择转录设备")
    p.add_argument("--local-only", action="store_true", help="仅本地模型与文件，不读取远程媒体")
    p.add_argument("--wait-for-controller", action="store_true", help=argparse.SUPPRESS)
    return p


def main(argv=None):
    parser = build_parser()
    args   = parser.parse_args(argv)
    if args.wait_for_controller and sys.stdin.readline().strip() != "ready":
        parser.error("桌面任务控制器未就绪")
    if args.transcribe_only and args.srt:
        parser.error("已有字幕请直接嵌入，不要同时指定 --transcribe-only")
    if args.font_size < 1:
        parser.error("--font-size 必须是正整数")

    if args.font == "Microsoft YaHei" and platform.system() == "Darwin":
        args.font = "PingFang SC"

    if not args.videos and not args.batch:
        check_deps()
        interactive_mode()
        return 0

    video_files = []
    for pattern in args.videos:
        expanded = glob.glob(pattern)
        video_files.extend(expanded if expanded else [pattern])

    if args.batch:
        cwd = Path(".")
        video_files = sorted(p for p in cwd.iterdir()
                             if p.is_file() and p.suffix.lower() in {".mp4", ".mkv"}
                             and not p.stem.endswith("_subtitled"))
        if not video_files:
            warn("当前目录没有找到 mp4/mkv 文件")
            return 1
        info(f"批量模式：找到 {len(video_files)} 个文件")

    if args.output and len(video_files) != 1:
        parser.error("--output 只能用于单个视频，批量处理不能共用输出文件")
    check_deps(require_asr=not bool(args.srt))
    failures = 0
    for v in video_files:
        try:
            process_one(Path(v), args)
        except (OSError, ValueError, RuntimeError) as exc:
            error(str(exc))
            failures += 1

    if failures:
        error(f"{failures} 个文件处理失败，其余已完成；请检查上述错误")
        return 1
    title("✅ 全部完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
