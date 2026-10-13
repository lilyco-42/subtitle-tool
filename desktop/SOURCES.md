# Shared source attribution

This application wraps the original `subtitle_tool.py` from this repository. It does not implement a second Whisper or FFmpeg engine.

React toolchain locks, the semantic theme, four unchanged shadcn primitives and Windows process-tree ownership originate from `lilyco-42/lilyco`, commit `e5f9fd66fa69be3e027697d7d2bffe8bc54e5ea0`, `apps/vision-studio/` (MIT). Full notice: `SHARED-SOURCE-LICENSE`. Registry URLs and exact primitive hashes: `ui/src/shadcn-sources.json`; original MIT notice: `ui/src/components/ui/LICENSE.md`.

Subtitle documents are parsed with `srt` 3.5.3; API: https://srt.readthedocs.io/en/latest/api.html . Distribution must retain its MIT license and all resolved dependency notices.

## Not yet a distributable release

Current code is a workbench implementation. A release additionally requires a pinned local Whisper model and its license/file manifest, a reviewed FFmpeg build with full notices and corresponding source, original CLI binary freezing, WebView2 SDK notices, real ASR and video/UI tests, native-window cleanup and installed/uninstalled tests. CI-only FFmpeg used by regressions is not a distributable bundle. No claimed price, sales or complete product acceptance follows from source or UI build alone.
