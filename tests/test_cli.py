"""Desktop prerequisite regressions; execute only in GitHub Actions."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import subtitle_tool as tool


class CliTests(unittest.TestCase):
    def test_help_does_not_require_model_or_ffmpeg(self):
        with patch.object(tool, "check_deps") as deps, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                tool.main(["--help"])
        self.assertEqual(0, result.exception.code)
        deps.assert_not_called()

    def test_batch_does_not_prompt_or_reprocess_generated_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path.cwd()
            try:
                os.chdir(directory)
                Path("video.MP4").write_bytes(b"fixture")
                Path("video_subtitled.mp4").write_bytes(b"completed fixture")
                with patch.object(tool, "check_deps"), patch.object(tool, "process_one") as process, \
                        patch.object(tool, "interactive_mode") as prompt, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, tool.main(["--batch", "--srt", "own.srt"]))
                prompt.assert_not_called()
                self.assertEqual([Path("video.MP4")], [call.args[0] for call in process.call_args_list])
            finally:
                os.chdir(original)

    def test_failure_is_not_reported_as_success_and_batch_continues(self):
        output = io.StringIO()
        with patch.object(tool, "check_deps"), patch.object(tool, "process_one",
                side_effect=[FileNotFoundError("missing video"), Path("result.mp4")]) as process, \
                contextlib.redirect_stdout(output):
            self.assertEqual(1, tool.main(["absent.mp4", "valid.mp4", "--srt", "own.srt"]))
        self.assertEqual(2, process.call_count)
        self.assertNotIn("全部完成", output.getvalue())

    def test_batch_output_collision_rejected_before_processing(self):
        with patch.object(tool, "check_deps") as deps, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                tool.main(["a.mp4", "b.mp4", "--output", "same.mp4"])
        self.assertEqual(2, result.exception.code)
        deps.assert_not_called()

    def test_onefile_extraction_directory_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            Path(directory, executable).write_bytes(b"not executed")
            with patch.object(tool.shutil, "which", return_value=None), \
                    patch.object(sys, "_MEIPASS", directory, create=True), \
                    patch.dict(os.environ, {"PATH": "original"}), contextlib.redirect_stdout(io.StringIO()):
                tool.check_deps(require_asr=False)
                self.assertEqual(directory, os.environ["PATH"].split(os.pathsep)[0])


class RealMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("Real FFmpeg and FFprobe are required; do not skip media tests")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="subtitle-real-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.video = self.root / "input.mp4"
        self.srt = self.root / "字幕 bob's [draft], notes.srt"
        self.srt.write_text("1\n00:00:00,100 --> 00:00:01,800\nNEW CAPTION\n\n", encoding="utf-8")
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i",
                        "color=c=black:s=320x240:r=12:d=2", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", "-c:v", "mpeg4", "-c:a", "aac",
                        "-shortest", str(self.video)], check=True, capture_output=True)

    def streams(self, path):
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)["streams"]

    def test_soft_codec_uses_output_and_replaces_old_subtitle(self):
        old_srt = self.root / "old.srt"
        old_srt.write_text("1\n00:00:00,100 --> 00:00:01,800\nOLD CAPTION\n\n", encoding="utf-8")
        old_video = self.root / "old.mkv"
        tool.embed_subtitle(self.video, old_srt, "soft", "Arial", 22, old_video)
        result = self.root / "new.mp4"
        tool.embed_subtitle(old_video, self.srt, "soft", "Arial", 22, result)
        streams = self.streams(result)
        self.assertEqual(1, sum(s["codec_type"] == "video" for s in streams))
        self.assertEqual(1, sum(s["codec_type"] == "audio" for s in streams))
        self.assertEqual(["mov_text"], [s["codec_name"] for s in streams if s["codec_type"] == "subtitle"])
        captions = subprocess.run(["ffmpeg", "-nostdin", "-i", str(result), "-map", "0:s:0", "-f", "srt", "-"],
                                  check=True, capture_output=True, text=True).stdout
        self.assertIn("NEW CAPTION", captions)
        self.assertNotIn("OLD CAPTION", captions)

    def test_hard_subtitle_special_path_changes_actual_frame(self):
        result = self.root / "hard output.mp4"
        font = "Arial" if os.name == "nt" else "DejaVu Sans"
        with patch.object(tool.subprocess, 'run', wraps=subprocess.run) as actual:
            tool.embed_subtitle(self.video, self.srt, "hard", font, 22, result)
        scratch = Path(actual.call_args.kwargs['cwd']).resolve()
        self.assertEqual(self.root, scratch.parent)
        self.assertFalse(scratch.exists(), 'Normal export left subtitle scratch files')
        frames = []
        for path in (self.video, result):
            frames.append(subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-ss", "0.5",
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                            check=True, capture_output=True).stdout)
        self.assertEqual(320 * 240, len(frames[0]))
        self.assertEqual(len(frames[0]), len(frames[1]))
        self.assertGreater(sum(frames[1]) / len(frames[1]), sum(frames[0]) / len(frames[0]) + 0.5)
        self.assertFalse(any(s["codec_type"] == "subtitle" for s in self.streams(result)))

    def test_missing_file_exits_nonzero_and_input_cannot_be_overwritten(self):
        result = subprocess.run([sys.executable, "subtitle_tool.py", str(self.root / "absent.mp4"),
                                 "--srt", str(self.srt)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(1, result.returncode)
        self.assertNotIn("全部完成", result.stdout)
        original = self.video.read_bytes()
        with self.assertRaises(ValueError):
            tool.embed_subtitle(self.video, self.srt, "soft", "Arial", 22, self.video)
        self.assertEqual(original, self.video.read_bytes())


if __name__ == "__main__":
    unittest.main()
