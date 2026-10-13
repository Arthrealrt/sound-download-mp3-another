"""Real model and codec smoke test. Downloads model on first run."""
import math
import struct
import sys
import tempfile
import threading
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import imageio_ffmpeg
from core import FORMATS, Job, encoder_args, run_command, separate


def main():
    with tempfile.TemporaryDirectory(prefix="sound-integration-") as folder:
        root = Path(folder)
        source = root / "测试 audio.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(b"".join(struct.pack("<hh", int(9000 * math.sin(i * 2 * math.pi * 440 / 44100)),
                                                  int(7000 * math.sin(i * 2 * math.pi * 660 / 44100)))
                                      for i in range(44100 * 2)))
        cancel = threading.Event()
        result = separate(Job(source, root / "exports", "WAV"), cancel, print,
                          lambda value, text: print(value, text, flush=True))
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        for stem in ("original", "vocals", "accompaniment"):
            wav = result / (stem + ".wav")
            for format, suffix in FORMATS.items():
                target = result / (stem + suffix)
                if format != "WAV":
                    run_command(encoder_args(ffmpeg, wav, target, format, "320"), cancel, print)
                assert target.stat().st_size > 100, target
                decoded = result / f"decoded_{stem}_{format}.wav"
                run_command([ffmpeg, "-v", "error", "-nostdin", "-i", str(target), "-c:a", "pcm_s16le",
                             str(decoded)], cancel, print)
                with wave.open(str(decoded)) as check:
                    assert check.getnchannels() == 2
                    assert 1.9 < check.getnframes() / check.getframerate() < 2.1
                print("PASS:", target.name, flush=True)
        print(f"PASS: real Demucs separation and all {3 * len(FORMATS)} exports decode correctly.", flush=True)


if __name__ == "__main__":
    main()
