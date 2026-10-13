import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Cancelled, Job, encoder_args, run_command, separate


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "中文 空格 & song.wav"
        self.source.write_bytes(b"sample")
        self.output = self.root / "exports"

    def test_reject_empty_missing_and_unsupported(self):
        for name in ["missing.wav", "empty.wav", "file.txt"]:
            path = self.root / name
            if name != "missing.wav":
                path.write_bytes(b"" if name == "empty.wav" else b"a")
            with self.assertRaises(ValueError):
                Job(path, self.output).validate()
        for fmt, rate in [("EXE", "320"), ("MP3", "999")]:
            with self.assertRaises(ValueError):
                Job(self.source, self.output, fmt, rate).validate()

    def test_format_and_paths(self):
        args = encoder_args("ffmpeg", self.source, self.output / "v.mp3", "MP3", "320")
        self.assertIn(str(self.source), args)
        self.assertIn("320k", args)
        self.assertIn("pcm_s24le", encoder_args("ffmpeg", self.source, self.output / "v.wav", "WAV", "320"))

    def test_subprocess_failure_and_cancel(self):
        logs = []
        with self.assertRaisesRegex(RuntimeError, "failure marker"):
            run_command([sys.executable, "-c", "print('failure marker'); exit(2)"], threading.Event(), logs.append)
        cancel = threading.Event()
        timer = threading.Timer(0.3, cancel.set)
        timer.start()
        started = time.monotonic()
        with self.assertRaises(Cancelled):
            run_command([sys.executable, "-c", "import time; time.sleep(20)"], cancel, logs.append)
        timer.join()
        self.assertLess(time.monotonic() - started, 4)

    def fake_command(self, args, cancel, log, env=None):
        if "demucs" in args:
            folder = Path(args[args.index("-o") + 1]) / "htdemucs" / "input"
            folder.mkdir(parents=True)
            for name in ("vocals.wav", "no_vocals.wav"):
                (folder / name).write_bytes(b"stem")
        else:
            Path(args[-1]).write_bytes(b"audio")

    def test_success_does_not_overwrite_and_cleans_scratch(self):
        with patch("core.run_command", side_effect=self.fake_command):
            first = separate(Job(self.source, self.output), threading.Event(), lambda _: None, lambda *_: None)
            second = separate(Job(self.source, self.output), threading.Event(), lambda _: None, lambda *_: None)
        self.assertNotEqual(first, second)
        self.assertEqual({p.name for p in first.iterdir()}, {"original.mp3", "vocals.mp3", "accompaniment.mp3"})
        self.assertFalse(list(self.output.glob(".sound-job-*")))

    def test_failure_and_cancel_publish_nothing(self):
        for failure in (RuntimeError("conversion failure"), Cancelled()):
            def command(args, cancel, log, env=None):
                if str(args[-1]).endswith("vocals.mp3"):
                    raise failure
                self.fake_command(args, cancel, log, env)
            with patch("core.run_command", side_effect=command):
                with self.assertRaises(type(failure)):
                    separate(Job(self.source, self.output), threading.Event(), lambda _: None, lambda *_: None)
            self.assertEqual(list(self.output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
