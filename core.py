"""Local audio separation and transactional export; UI-independent."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

FORMATS = {"MP3": ".mp3", "WAV": ".wav", "FLAC": ".flac", "M4A": ".m4a", "OGG": ".ogg"}
INPUT_TYPES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".ape", ".webm", ".mp4", ".mkv"}
MAX_BYTES = 500 * 1024 * 1024


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Job:
    source: Path
    destination: Path
    format: str = "MP3"
    bitrate: str = "320"
    key_file: Path | None = None
    key_db: Path | None = None

    def validate(self):
        if not self.source.is_file():
            raise ValueError("请先选择有效的音频文件。")
        from media import encrypted_extensions
        if self.source.suffix.lower() not in INPUT_TYPES | encrypted_extensions():
            raise ValueError("不支持这个文件类型，请选择 MP3、WAV、FLAC 或其他音频文件。")
        size = self.source.stat().st_size
        if size == 0 or size > MAX_BYTES:
            raise ValueError("音频不能为空，文件大小不能超过 500 MB。")
        if self.format not in {*FORMATS, "KEEP"} or self.bitrate not in {"128", "192", "256", "320"}:
            raise ValueError("导出格式或码率无效。")


def run_command(args: list[str], cancel: threading.Event, log: Callable[[str], None], env=None, limit_dir=None):
    if cancel.is_set():
        raise Cancelled("已取消")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", env=env,
                               creationflags=flags)
    tail: list[str] = []

    def reader():
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line:
                tail.append(line)
                del tail[:-20]
                log(line)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        while process.poll() is None:
            if limit_dir:
                total = 0
                for path in Path(limit_dir).glob("media.*"):
                    try:
                        total += path.stat().st_size
                    except FileNotFoundError:
                        pass  # Downloader may rename a completed .part file.
                if total > MAX_BYTES:
                    raise ValueError("下载内容超过 500 MB，已停止下载。")
            if cancel.wait(0.15):
                process.kill()
                process.wait()
                raise Cancelled("已取消，临时文件已清理。")
        thread.join()
        if cancel.is_set():
            raise Cancelled("已取消，临时文件已清理。")
        if process.returncode:
            raise RuntimeError("处理失败：\n" + "\n".join(tail[-8:]))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        thread.join(timeout=2)
        if process.stdout:
            process.stdout.close()


def encoder_args(ffmpeg: str, source: Path, target: Path, format: str, bitrate: str):
    options = {"MP3": ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"],
               "WAV": ["-c:a", "pcm_s24le"], "FLAC": ["-c:a", "flac"],
               "M4A": ["-c:a", "aac", "-b:a", "256k"], "OGG": ["-c:a", "libvorbis", "-q:a", "6"]}
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
            "-map", "0:a:0", "-vn", *options[format], str(target)]


def separate(job: Job, cancel: threading.Event, log: Callable[[str], None],
             progress: Callable[[int, str], None]) -> Path:
    job.validate()
    if job.format == "KEEP":
        raise ValueError("分离任务请选择 MP3、WAV、FLAC、M4A 或 OGG。")
    if cancel.is_set():
        raise Cancelled()
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    job.destination.mkdir(parents=True, exist_ok=True)
    # Same filesystem makes final rename atomic. Failed/cancelled jobs publish nothing.
    with tempfile.TemporaryDirectory(prefix=".sound-job-", dir=job.destination) as scratch:
        root = Path(scratch)
        from media import prepare_source, embed_metadata
        source, metadata = prepare_source(job, root, cancel, log)
        normalized = root / "input.wav"
        progress(5, "正在读取音频")
        run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i",
                     str(source), "-map", "0:a:0", "-vn", "-ac", "2", "-ar",
                     "44100", "-c:a", "pcm_s16le", str(normalized)], cancel, log)
        progress(15, "正在分离人声和伴奏（首次运行可能下载模型）")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["TORCH_HOME"] = str(Path(__file__).resolve().parent / ".cache" / "torch")
        run_command([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs",
                     "-d", "cpu", "-j", "0", "--shifts", "0", "-o", str(root / "stems"),
                     str(normalized)], cancel, log, env)
        stem_dir = root / "stems" / "htdemucs" / "input"
        sources = {"original": source, "vocals": stem_dir / "vocals.wav",
                   "accompaniment": stem_dir / "no_vocals.wav"}
        if not all(path.is_file() for path in sources.values()):
            raise RuntimeError("分离模型没有生成预期文件，请查看日志。")
        result = root / "result"
        result.mkdir()
        for index, (name, source) in enumerate(sources.items()):
            progress(80 + index * 5, f"正在导出 {name}")
            run_command(encoder_args(ffmpeg, source, result / (name + FORMATS[job.format]),
                                     job.format, job.bitrate), cancel, log)
            if name == "original":
                embed_metadata(result / (name + FORMATS[job.format]), metadata)
        if cancel.is_set():
            raise Cancelled()
        safe_stem = job.source.stem[:60].rstrip(" .") or "audio"
        final = job.destination / f"{safe_stem}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        result.rename(final)
    progress(100, "完成：原曲、人声、伴奏已保存")
    return final
