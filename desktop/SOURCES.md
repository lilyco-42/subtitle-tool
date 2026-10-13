# Shared source attribution

This application wraps the original `subtitle_tool.py` from this repository. It does not implement a second Whisper or FFmpeg engine.

`packaging/native-attribution.py` preserves actual installed distribution notices,
original frontend notices, runtime notices and the application's current Git
source archive. PyAV 16.0.1 is pinned to upstream `PyAV-Org/PyAV` commit
`7687256d87f22f78cb75bb4aba94dc6e504c9983`; its `scripts/ffmpeg-8.0.json`
selects pyav-ffmpeg release `8.0-2`, builder commit
`fab22bcb12748a05f86683ac632fdb96994d970e`. The builder's literal source SHA
table is parsed without executing upstream code; full dependency archives and
original notices are preserved separately from the standalone FFmpeg CLI sources.
The compiled wheel's actual FFmpeg version/configuration/license and frozen
native-file hashes are recorded. Unresolved runtime attribution is a release
blocker, not evidence of a compatible license.

The per-user NSIS installer generator is adapted from `lilyco-42/lilyco`, commit
`a308ad03671a2b8d415b85ff2d7e2e7bfc42796b`, `apps/vision-studio/packaging/windows-installer.py`.
Its MIT notice remains in `SHARED-SOURCE-LICENSE`. The subtitle-specific installed
processing acceptance tests the original engine and offline ASR, plus exact
file-list uninstall while retaining unrelated user files.

React toolchain locks, the semantic theme, four unchanged shadcn primitives and Windows process-tree ownership originate from `lilyco-42/lilyco`, commit `e5f9fd66fa69be3e027697d7d2bffe8bc54e5ea0`, `apps/vision-studio/` (MIT). Full notice: `SHARED-SOURCE-LICENSE`. Registry URLs and exact primitive hashes: `ui/src/shadcn-sources.json`; original MIT notice: `ui/src/components/ui/LICENSE.md`.

Subtitle documents are parsed with `srt` 3.5.3; API: https://srt.readthedocs.io/en/latest/api.html . Distribution must retain its MIT license and all resolved dependency notices.

The native-window close helper and independent SDK pins come from `lilyco-42/lilyco`,
commit `a308ad03671a2b8d415b85ff2d7e2e7bfc42796b`, under the same preserved MIT notice.
Microsoft.Web.WebView2 1.0.3856.49 has its own BSD-3-Clause license;
`MICROSOFT-WEBVIEW2-LICENSE.txt` preserves its exact original bytes. Windows Actions verify
the official NuGet package SHA, full license and all five original frozen DLLs, independently
of pywebview's license. This SDK is distinct from the installed Microsoft WebView2 Runtime.

## Not yet a distributable release

The `Subtitle reviewed media` pipeline compiles FFmpeg `n8.0.1`, exact commit
`894da5ca7d742e4429ffb2af534fcda0103ef593`, using the existing BtbN recipes at
`63ac3265b0789ea16c7b1f8351cd2ad195a28722`. Only subtitle-related external libraries
are selected; FFmpeg's built-in format/decoder/filter support stays enabled.
GPL/version3 are enabled, nonfree is not selected, and network input is disabled.
The source archives actually consumed by the library build, exact FFmpeg source,
configuration, builder source and local patch accompany the resulting binary.
Future delivery must retain both binary and complete corresponding sources.
This media component does not prove the frozen application's complete distribution
or its installed/uninstalled behavior; these remain separate release gates.

Current code is a workbench implementation. A release additionally requires a pinned local Whisper model and its license/file manifest, a reviewed FFmpeg build with full notices and corresponding source, original CLI binary freezing, WebView2 SDK notices, real ASR and video/UI tests, native-window cleanup and installed/uninstalled tests. CI-only FFmpeg used by regressions is not a distributable bundle. No claimed price, sales or complete product acceptance follows from source or UI build alone.
