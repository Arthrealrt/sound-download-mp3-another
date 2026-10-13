"""Download, decrypt and convert using local transactional output directories."""
import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from core import Cancelled, FORMATS, MAX_BYTES, Job, encoder_args, run_command


def encrypted_extensions():
    from music_unlock.formats import supported_extensions
    return set(supported_extensions()) | {".kgg"}


def is_encrypted(path):
    if path.suffix.lower() in encrypted_extensions() or path.name.lower().endswith((".kgm.flac", ".vpr.flac")):
        return True
    with path.open("rb") as stream:
        header = stream.read(16)
    from music_unlock.formats.kgm import KGM_MAGIC, VPR_MAGIC
    return header[:8] == b"CTENFDAM" or header in (KGM_MAGIC, VPR_MAGIC)


def prepare_source(job, scratch, cancel, log):
    if not is_encrypted(job.source):
        return job.source.resolve(), {}
    log("正在转换加密音乐文件…")
    args = [sys.executable, str(Path(__file__).with_name("decrypt_worker.py")),
            str(job.source.resolve()), str(scratch)]
    for flag, path in (("--key-file", job.key_file), ("--key-db", job.key_db)):
        if path:
            if not path.is_file():
                raise ValueError("密钥文件或密钥数据库不存在。")
            args.extend([flag, str(path.resolve())])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    run_command(args, cancel, log, env)
    files = list(scratch.glob("decoded.*"))
    if len(files) != 1:
        raise RuntimeError("解码器未生成音频文件。")
    metadata = json.loads((scratch / "metadata.json").read_text(encoding="utf-8"))
    return files[0], metadata


def embed_metadata(target, metadata):
    if metadata:
        from music_unlock.tags import embed
        cover = base64.b64decode(metadata["cover"]) if metadata.get("cover") else None
        embed(target.suffix[1:], target, metadata.get("tags", {}), cover)


def publish(result, destination, label):
    final = destination / f"{label}_{uuid.uuid4().hex[:10]}"
    result.rename(final)
    return final


@dataclass(frozen=True)
class ConversionResult:
    directory: Path
    files: tuple[Path, ...]
    failures: tuple[str, ...] = ()


def convert_files(jobs, cancel, log, progress):
    if not jobs:
        raise ValueError("请先选择要转换的音频文件。")
    destination = jobs[0].destination
    destination.mkdir(parents=True, exist_ok=True)
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    failures, saved = [], []
    with tempfile.TemporaryDirectory(prefix=".convert-job-", dir=destination) as scratch:
        root = Path(scratch)
        result = root / "result"
        result.mkdir()
        for index, job in enumerate(jobs):
            if cancel.is_set():
                raise Cancelled()
            progress(int(index * 95 / len(jobs)), f"正在转换 {index + 1}/{len(jobs)}：{job.source.name}")
            try:
                job.validate()
                if job.destination != destination:
                    raise ValueError("批量任务必须使用相同的输出目录。")
                with tempfile.TemporaryDirectory(dir=root) as item_temp:
                    source, metadata = prepare_source(job, Path(item_temp), cancel, log)
                    suffix = source.suffix.lower() if job.format == "KEEP" else FORMATS[job.format]
                    stem = job.source.stem[:70].rstrip(" .") or "audio"
                    target = result / f"{index + 1:03d}_{stem}{suffix}"
                    if job.format == "KEEP":
                        shutil.copyfile(source, target)
                    else:
                        run_command(encoder_args(ffmpeg, source, target, job.format, job.bitrate), cancel, log)
                    embed_metadata(target, metadata)
                    if cancel.is_set():
                        raise Cancelled()
                    saved.append(target.name)
                    log("已转换：" + job.source.name)
            except Cancelled:
                raise
            except Exception as exc:
                # Discard any partial encoder output for this item.
                for candidate in result.glob(f"{index + 1:03d}_*"):
                    candidate.unlink(missing_ok=True)
                failure = job.source.name + "：" + str(exc)
                failures.append(failure)
                log(failure)
        if not saved:
            raise RuntimeError("没有文件转换成功：\n" + "\n".join(failures[-5:]))
        if cancel.is_set():
            raise Cancelled()
        if failures:
            (result / "conversion-errors.txt").write_text("\n\n".join(failures), encoding="utf-8")
        final = publish(result, destination, "converted")
    progress(100, f"转换完成：成功 {len(saved)}，失败 {len(failures)}")
    return ConversionResult(final, tuple(final / name for name in saved), tuple(failures))


def validate_url(url):
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        _ = parts.port
    except ValueError:
        raise ValueError("请输入完整的 HTTP/HTTPS 音频或网页链接，不能包含账号密码。") from None


def download_audio(url, destination, format, bitrate, cancel, log, progress):
    url = url.strip()
    validate_url(url)
    if format not in FORMATS or bitrate not in {"128", "192", "256", "320"}:
        raise ValueError("下载任务的音频格式或码率无效。")
    import imageio_ffmpeg
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-job-", dir=destination) as scratch:
        root = Path(scratch)
        progress(5, "正在解析链接和下载音频")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # Ignore user yt-dlp configs and plugins: predictable single-item downloads.
        run_command([sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-plugin-dirs",
                     "--no-playlist", "--playlist-items", "1", "--newline", "--no-colors",
                     "--socket-timeout", "15", "--retries", "2", "--fragment-retries", "2",
                     "--max-filesize", str(MAX_BYTES), "-f", "bestaudio/best", "-o",
                     str(root / "media.%(ext)s"), "--", url], cancel, log, env, limit_dir=root)
        downloaded = [p for p in root.glob("media.*") if p.is_file() and p.suffix not in {".part", ".ytdl", ".temp"}]
        if len(downloaded) != 1:
            raise RuntimeError("未下载到单个有效音频；文件可能超过 500 MB，或该网站链接不受支持。")
        source = downloaded[0]
        if not 0 < source.stat().st_size <= MAX_BYTES:
            raise ValueError("下载文件为空或超过 500 MB。")
        progress(85, "下载完成，正在转为所选音频格式")
        result = root / "result"
        result.mkdir()
        target = result / ("downloaded_audio" + FORMATS[format])
        run_command(encoder_args(imageio_ffmpeg.get_ffmpeg_exe(), source, target, format, bitrate), cancel, log)
        if cancel.is_set():
            raise Cancelled()
        final = publish(result, destination, "download")
    progress(100, "网上音频下载完成，可用于人声与伴奏分离")
    return ConversionResult(final, (final / target.name,))
