# 声伴 Sound Studio

Windows 中文桌面音频工具，支持**网上下载、普通及加密音乐格式转换、人声与伴奏分离**。导出格式支持 **MP3 / WAV / FLAC / M4A / OGG**。分离时输出原曲、人声、伴奏三份文件；原曲指完整混音。

## 开始使用

1. 安装 [Python 3.12.10（64 位）](https://www.python.org/downloads/release/python-31210/) 或 3.11，保留 pip、Tcl/Tk、Python Launcher，勾选 Add Python to PATH。本项目不支持 Python 3.15；可同时安装 3.12。
2. 下载本仓库 ZIP 并解压到你有写入权限的目录。双击 `install.bat`，首次安装需联网，依赖下载体积较大。
3. 双击 `start.bat` 打开中文桌面界面。
4. 选择音频、保存目录、格式，点击“开始分离并导出”。完成后点击“打开结果目录”。

**从旧版本升级**：关闭软件，用新版文件替换旧版项目文件，然后重新运行 `install.bat` 安装新增依赖，最后运行 `start.bat`。保留现有 `.venv` 和 `.cache` 即可。

## 网上音频下载

1. 选择“网上下载”标签，粘贴完整 HTTP/HTTPS 音频直链或 yt-dlp 支持的网页链接。
2. 选择保存目录和格式，点击“下载并转换音频”。仅下载单个条目，不批量下载播放列表。
3. 完成后点击“将结果用于分离”，再点击“开始分离并导出”。

下载结果保存在独立 `download_随机编号` 目录。使用 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 解析网页，FFmpeg 转换音频。部分网站要求登录、额外 JavaScript 运行环境或禁止下载；本版没有登录、Cookie 导入或付费资源获取功能，不能保证所有网站链接可用。HTTP 下载已用本机测试服务器实际验证，没有逐个验证外部网站。

单次下载内容限制为 500 MB，失败或取消会删除临时下载；日志显示实际下载进度。如果网站改动导致解析失败，可在项目目录运行 `.venv\Scripts\python.exe -m pip install --upgrade yt-dlp` 更新下载器。

## 普通 / 加密音乐格式转换

选择“格式转换 / 加密音乐”标签，可多选文件后批量转换。普通音频支持转为 MP3、FLAC、M4A、WAV、OGG；选择“保持原格式”时，普通文件保持内容，加密文件仅解密、不重新编码。

已集成 [HRuiCcc/music-geshizhuanhuan](https://github.com/HRuiCcc/music-geshizhuanhuan) 的本地转换引擎，保留 [MIT 许可证](licenses/music-geshizhuanhuan-MIT.txt)；来源版本见 [THIRD_PARTY.md](THIRD_PARTY.md)。

| 平台 | 主要格式 | 限制 |
| --- | --- | --- |
| 网易云 | NCM | 转换后在 MP3 / FLAC / M4A 中写入可提取的标签和封面 |
| QQ 音乐 | QMC、MFLAC、MGG、BKCM 等 | 部分新版文件需要外部 EKey 或 player_process_db 密钥库 |
| 酷狗 | KGM、KGMA、VPR | 沿用上游支持的变体，KGG v5 暂不支持 |
| 酷我 | KWM | 支持上游旧版格式 |

需要外部 QQ 密钥时，在对应选择框中选择含 EKey 的 UTF-8 文本文件或密钥数据库；不必把密钥内容粘贴进日志。部分文件变体不受支持，失败原因会显示在日志中。

转换成功的文件保存在独立 `converted_随机编号` 目录，不覆盖原文件。批次中某个文件失败时继续其他文件，错误记录保存在 `conversion-errors.txt`。取消整个批次时不发布该批次的输出。完成后可将首个成功文件用于分离；分离入口也可直接导入支持的加密文件。

输出示例：

```text
Music/SoundStudio/歌曲名_日期_随机编号/
  original.mp3       # 完整原曲（按所选格式转码）
  vocals.mp3         # 人声
  accompaniment.mp3 # 伴奏
```

支持普通输入 MP3、WAV、FLAC、M4A、AAC、OGG、OPUS、WMA、AIFF、APE；也可读取视频文件中的音轨。实际解码取决于 FFmpeg，单文件上限 500 MB。MP3 可选 128 / 192 / 256 / 320 kbps，WAV 为 24 位 PCM，FLAC 为无损编码，M4A 为 AAC 256 kbps，OGG 为 Vorbis 质量等级 6。将有损原曲转为 WAV 或 FLAC 不会恢复已经丢失的音质。

## 工作方式

- 使用 [Demucs 4 / htdemucs](https://github.com/facebookresearch/demucs) 分离，默认 CPU，无需显卡。
- 第一次分离会从模型发布服务下载模型并缓存到 `.cache/torch`。完成下载后，相同模型可离线使用。
- 音频在本机处理，不上传歌曲。CPU 分离可能耗时数分钟到更久，取决于音频长度和电脑性能；建议先用短音频尝试。
- 进度条表示“读取 → 分离 → 导出”阶段，并非模型内部的精确剩余时间。日志显示模型的详细进度。
- 支持取消。失败或取消会清理临时文件，不发布不完整结果。每次成功生成独立目录，避免覆盖已有结果。
- 每次导出三份同格式音频；再次处理可选择不同格式。分离可能存在人声残留或音质变化，不能保证与官方伴奏一致。

这个版本是**带安装脚本的 Python 桌面应用源代码**，不是免安装 EXE。网络下载通过 yt-dlp 处理支持的链接，加密格式转换在本机完成。

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

自动化测试覆盖参数校验、命令失败、取消、导出事务、五种编码器、四个平台的合成加密样本、QMC 外部 EKey、标签保留、批次部分失败以及实际 HTTP 下载。集成测试生成 2 秒合成音频，真实调用模型并检查三份音频各五种格式可解码；首次需下载模型。合成样本用于验证处理链，不用于评价真实歌曲的分离效果。

依赖版本：Python 3.11/3.12、PyTorch/Torchaudio 2.5.1 CPU、Demucs 4.0.1、NumPy 1.26.4。Demucs 上游已归档，故固定兼容版本。FFmpeg 通过 imageio-ffmpeg 提供，不需要手动安装。
