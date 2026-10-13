# 第三方组件

## music-geshizhuanhuan

- 来源：https://github.com/HRuiCcc/music-geshizhuanhuan
- 固定版本：`28f4ed0724f85978405d961c0e955266eed383ee`
- `music_unlock/` 与 `assets/kugou_key.xz` 从该版本原样复制。
- `tests/vendor_fixtures/` 保留该版本的合成测试构造器与音频样本。
- 完整 MIT 许可证和版权声明见 `licenses/music-geshizhuanhuan-MIT.txt`。
- 集成使用其解码与标签引擎；桌面界面、下载器和任务管理由本项目实现。未复制上游网页界面。

依赖 Demucs、PyTorch、Torchaudio、FFmpeg（imageio-ffmpeg）、yt-dlp、PyCryptodome、Mutagen；这些依赖保留各自许可证，安装时由各自发布渠道获取。
