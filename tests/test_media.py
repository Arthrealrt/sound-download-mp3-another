import functools
import http.server
import lzma
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).with_name("vendor_fixtures")))
from builders import FIXTURE_MP3, build_kgm, build_kwm, build_ncm, build_qmc_v1, build_stag, make_ekey_v1
from core import Cancelled, FORMATS, Job, run_command
from media import convert_files, download_audio, validate_url


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.mp3"
        self.source.write_bytes(FIXTURE_MP3)
        self.output = self.root / "output"
        self.cancel = threading.Event()

    def convert(self, sources, format="MP3", key_file=None):
        jobs = [Job(p, self.output, format, "320", key_file) for p in sources]
        return convert_files(jobs, self.cancel, lambda _: None, lambda *_: None)

    def assert_decodes(self, path):
        import imageio_ffmpeg
        run_command([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-nostdin", "-i", str(path),
                     "-f", "null", "-"], self.cancel, lambda _: None)

    def test_all_five_formats(self):
        for format, extension in FORMATS.items():
            result = self.convert([self.source], format)
            self.assertEqual(result.files[0].suffix, extension)
            self.assert_decodes(result.files[0])

    def test_encrypted_four_platforms_and_tags(self):
        metadata = {"format": "mp3", "musicName": "测试曲", "artist": [["测试歌手", 1]], "album": "测试专辑"}
        key = lzma.decompress((ROOT / "assets" / "kugou_key.xz").read_bytes())
        blobs = {"song.ncm": build_ncm(FIXTURE_MP3, b"0123456789abcdef", metadata),
                 "song.bkcmp3": build_qmc_v1(FIXTURE_MP3),
                 "song.kgm": build_kgm(FIXTURE_MP3, key),
                 "song.kwm": build_kwm(b"\x00" * 64 + FIXTURE_MP3)}
        paths = []
        for name, content in blobs.items():
            path = self.root / name
            path.write_bytes(content)
            paths.append(path)
        result = self.convert(paths)
        self.assertEqual(len(result.files), 4)
        self.assertFalse(result.failures)
        for file in result.files:
            self.assert_decodes(file)
        from mutagen.id3 import ID3
        self.assertEqual(ID3(result.files[0])["TIT2"].text[0], "测试曲")

    def test_qmc_external_ekey(self):
        master = bytes(range(24))
        path = self.root / "keyed.mflac"
        path.write_bytes(build_stag(FIXTURE_MP3, master))
        with self.assertRaises(RuntimeError):
            self.convert([path])
        keyfile = self.root / "ekey.txt"
        keyfile.write_text(make_ekey_v1(master), encoding="utf-8")
        result = self.convert([path], key_file=keyfile)
        self.assert_decodes(result.files[0])

    def test_keep_format_and_partial_failure(self):
        invalid = self.root / "bad.kgg"
        invalid.write_bytes(b"unsupported")
        result = self.convert([invalid, self.source], "KEEP")
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.files[0].read_bytes(), FIXTURE_MP3)
        self.assertTrue((result.directory / "conversion-errors.txt").is_file())

    def test_cancel_does_not_publish(self):
        self.cancel.set()
        with self.assertRaises(Cancelled):
            self.convert([self.source])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_url_validation(self):
        for url in ("", "file:///test.mp3", "https://user:password@example.com/a", "ftp://example.com/a", "http://example.com:bad/a"):
            with self.assertRaises(ValueError):
                validate_url(url)
        validate_url("https://example.com/audio.mp3?x=1")

    def test_download_size_limit_stops_subprocess(self):
        (self.root / "media.mp3.part").write_bytes(b"x" * 20)
        with patch("core.MAX_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "500 MB"):
                run_command([sys.executable, "-c", "import time; time.sleep(20)"],
                            self.cancel, lambda _: None, limit_dir=self.root)

    def test_real_http_download_and_cleanup(self):
        handler = functools.partial(QuietHandler, directory=str(self.root))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/input.mp3"
            result = download_audio(url, self.output, "MP3", "192", self.cancel, lambda _: None, lambda *_: None)
            self.assert_decodes(result.files[0])
            self.assertFalse(list(self.output.glob(".download-job-*")))
            self.cancel.set()
            with self.assertRaises(Cancelled):
                download_audio(url, self.output, "MP3", "320", self.cancel, lambda _: None, lambda *_: None)
            self.assertFalse(list(self.output.glob(".download-job-*")))
            self.cancel.clear()
            (self.root / "page.html").write_text("<html>no audio</html>")
            with self.assertRaises(RuntimeError):
                download_audio(f"http://127.0.0.1:{server.server_port}/page.html", self.output, "MP3", "320", self.cancel, lambda _: None, lambda *_: None)
            self.assertFalse(list(self.output.glob(".download-job-*")))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
