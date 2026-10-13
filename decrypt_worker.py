"""Run the vendored decoder in a cancellable subprocess."""
import argparse
import base64
import json
from pathlib import Path

from music_unlock.formats import pick_decoder
from music_unlock.formats.base import DecodeOptions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--key-db", type=Path)
    args = parser.parse_args()
    try:
        key = None
        if args.key_file:
            if args.key_file.stat().st_size > 65536:
                raise ValueError("EKey 文本文件过大。")
            key = args.key_file.read_text(encoding="utf-8-sig").strip()
        result = pick_decoder(args.source).decode(args.source, DecodeOptions(ekey=key, ekey_db=args.key_db))
        if result.container not in {"mp3", "flac", "m4a", "wav", "ogg"} or not result.payload:
            raise ValueError("解密结果不是有效的音频容器，文件变体可能不受支持。")
        target = args.output / ("decoded." + result.container)
        target.write_bytes(result.payload)
        (args.output / "metadata.json").write_text(json.dumps({"tags": result.tags,
            "cover": base64.b64encode(result.cover).decode("ascii") if result.cover else None}), encoding="utf-8")
        print("解密完成：" + result.source)
        return 0
    except Exception as exc:
        print("加密格式转换失败：" + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
