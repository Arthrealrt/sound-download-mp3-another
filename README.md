# 声伴 Sound Studio

Windows 本地音频分离软件。选择一首本地音频，导出 **原曲、人声、伴奏** 三份文件，支持 **MP3 / WAV / FLAC**。原曲是含人声和伴奏的完整音频；人声是模型分离的 vocal；伴奏是去掉人声的 instrumental。

## 开始使用

1. 安装 [Python 3.12（64 位）](https://www.python.org/downloads/) 或 3.11，安装时保留 pip 和 Tcl/Tk，勾选 Add Python to PATH。
2. 下载本仓库 ZIP 并解压到你有写入权限的目录。双击 `install.bat`，首次安装需联网，依赖下载体积较大。
3. 双击 `start.bat` 打开中文桌面界面。
4. 选择音频、保存目录、格式，点击“开始分离并导出”。完成后点击“打开结果目录”。

输出示例：

```text
Music/SoundStudio/歌曲名_日期_随机编号/
  original.mp3       # 完整原曲（按所选格式转码）
  vocals.mp3         # 人声
  accompaniment.mp3 # 伴奏
```

支持输入 MP3、WAV、FLAC、M4A、AAC、OGG、OPUS、WMA、AIFF；实际解码取决于 FFmpeg，单文件上限 500 MB。MP3 可选 128 / 192 / 256 / 320 kbps，WAV 为 24 位 PCM，FLAC 为无损编码。将有损原曲转为 WAV 或 FLAC 不会恢复已经丢失的音质。

## 工作方式

- 使用 [Demucs 4 / htdemucs](https://github.com/facebookresearch/demucs) 分离，默认 CPU，无需显卡。
- 第一次分离会从模型发布服务下载模型并缓存到 `.cache/torch`。完成下载后，相同模型可离线使用。
- 音频在本机处理，不上传歌曲。CPU 分离可能耗时数分钟到更久，取决于音频长度和电脑性能；建议先用短音频尝试。
- 进度条表示“读取 → 分离 → 导出”阶段，并非模型内部的精确剩余时间。日志显示模型的详细进度。
- 支持取消。失败或取消会清理临时文件，不发布不完整结果。每次成功生成独立目录，避免覆盖已有结果。
- 每次导出三份同格式音频；再次处理可选择不同格式。分离可能存在人声残留或音质变化，不能保证与官方伴奏一致。

这个版本是**带安装脚本的 Python 桌面应用源代码**，不是免安装 EXE。不提供音乐平台搜索、付费歌曲抓取或平台链接解析；用于你已经保存到本地的音频。

## 常见问题

- **找不到 Python**：安装官方 64 位 Python 3.11/3.12，然后重新打开安装脚本。不使用 Windows 商店占位程序。
- **依赖或模型下载失败**：检查网络能否访问 PyPI、download.pytorch.org 和 dl.fbaipublicfiles.com，再重试。安装中断后可以再次运行 `install.bat`。
- **分离失败**：先确认原文件能播放，并检查磁盘剩余空间、输出目录权限和日志。
- **CPU 很慢 / 内存不足**：关闭其他大型程序，使用较短音频，确保有足够内存和磁盘空间存放中间 WAV。

## 开发和测试

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe tests\integration.py
```

单元测试覆盖参数校验、命令失败、取消和导出事务。集成测试生成 2 秒合成音频，真实调用模型并检查 MP3/WAV/FLAC 可解码；首次需下载模型。合成音频用于验证处理链，不用于评价歌曲分离效果。

依赖版本：Python 3.11/3.12、PyTorch/Torchaudio 2.5.1 CPU、Demucs 4.0.1、NumPy 1.26.4。Demucs 上游已归档，故固定兼容版本。FFmpeg 通过 imageio-ffmpeg 提供，不需要手动安装。
