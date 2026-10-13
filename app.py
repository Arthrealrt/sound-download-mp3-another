"""Sound Studio: Chinese Windows desktop interface."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import Cancelled, Job, separate
from media import ConversionResult, convert_files, download_audio, encrypted_extensions, validate_url


class App:
    def __init__(self, root):
        self.root = root
        root.title("声伴 · 音频分离工作室")
        root.geometry("940x850")
        root.minsize(840, 740)
        root.configure(bg="#f4f6fb")
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.result = None
        self.source = tk.StringVar()
        self.url = tk.StringVar()
        self.key_file = tk.StringVar()
        self.key_db = tk.StringVar()
        self.conversion_sources = []
        self.conversion_count = tk.StringVar(value="尚未选择文件")
        self.result_audio = None
        self.destination = tk.StringVar(value=str(Path.home() / "Music" / "SoundStudio"))
        self.format = tk.StringVar(value="MP3")
        self.bitrate = tk.StringVar(value="320")
        self.status = tk.StringVar(value="选择一首音频，开始制作你的伴奏")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6fb")
        style.configure("TLabel", background="#f4f6fb", foreground="#17223b", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 25, "bold"))
        style.configure("Hint.TLabel", foreground="#66718a", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", padding=(12, 9), font=("Microsoft YaHei UI", 10))
        style.configure("Primary.TButton", background="#4f46e5", foreground="white")
        style.map("Primary.TButton", background=[("active", "#4338ca"), ("disabled", "#a8aec2")])
        style.configure("TProgressbar", background="#4f46e5", troughcolor="#e1e5f0")
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="声伴 Sound Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="网上下载 · 普通与加密格式转换 · 人声和伴奏分离", style="Hint.TLabel").pack(anchor="w", pady=(4, 16))
        self.controls = []
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill="x", pady=(0, 14))
        local = ttk.Frame(self.tabs, padding=12)
        online = ttk.Frame(self.tabs, padding=12)
        conversion = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(local, text="  人声与伴奏分离  ")
        self.tabs.add(online, text="  网上下载  ")
        self.tabs.add(conversion, text="  格式转换 / 加密音乐  ")
        self.path_row(local, "选择本地音频（也支持已集成的加密格式）", self.source, self.choose_source, "浏览音频")
        ttk.Label(local, text="导出完整原曲、人声、伴奏三份文件。", style="Hint.TLabel").pack(anchor="w")
        ttk.Label(online, text="粘贴 HTTP/HTTPS 音频直链或下载器支持的网页链接").pack(anchor="w", pady=(0, 8))
        url_entry = ttk.Entry(online, textvariable=self.url, font=("Microsoft YaHei UI", 10))
        url_entry.pack(fill="x", ipady=6)
        self.controls.append((url_entry, "normal"))
        ttk.Label(online, text="下载单个音频并转换格式；完成后可点击“将结果用于分离”。\n部分网站需要登录或额外环境，无法保证所有链接可下载。", style="Hint.TLabel").pack(anchor="w", pady=10)
        batch_row = ttk.Frame(conversion)
        batch_row.pack(fill="x", pady=(0, 8))
        batch_button = ttk.Button(batch_row, text="选择一个或多个文件", command=self.choose_conversion)
        batch_button.pack(side="left")
        self.controls.append((batch_button, "normal"))
        ttk.Label(batch_row, textvariable=self.conversion_count, style="Hint.TLabel").pack(side="left", padx=12)
        self.path_row(conversion, "QQ EKey 文本（可选）", self.key_file,
                      lambda: self.choose_key(self.key_file), "选择 EKey", compact=True)
        self.path_row(conversion, "QQ 密钥库（可选）", self.key_db,
                      lambda: self.choose_key(self.key_db), "选择密钥库", compact=True)
        ttk.Label(conversion, text="集成 NCM / QMC / KGM / KWM 引擎；新版 KGG 不支持，部分 QMC 需要密钥。", style="Hint.TLabel").pack(anchor="w")
        self.tabs.bind("<<NotebookTabChanged>>", lambda _: self.update_mode())
        self.path_row(frame, "02  保存到", self.destination, self.choose_destination, "选择目录")
        options = ttk.Frame(frame)
        options.pack(fill="x", pady=(10, 20))
        ttk.Label(options, text="03  导出格式").pack(side="left")
        self.formats = ttk.Combobox(options, textvariable=self.format, values=["MP3", "WAV", "FLAC", "M4A", "OGG"], width=12, state="readonly")
        formats = self.formats
        formats.pack(side="left", padx=12)
        formats.bind("<<ComboboxSelected>>", lambda _: self.update_bitrate())
        self.controls.append((formats, "readonly"))
        ttk.Label(options, text="MP3 码率").pack(side="left", padx=(14, 0))
        self.rate = ttk.Combobox(options, textvariable=self.bitrate, values=["128", "192", "256", "320"], width=7, state="readonly")
        self.rate.pack(side="left", padx=12)
        ttk.Label(options, text="kbps", style="Hint.TLabel").pack(side="left")
        self.controls.append((self.rate, "readonly"))
        ttk.Label(frame, text="分离输出三份音频；下载和格式转换输出普通音频文件。", style="Hint.TLabel").pack(anchor="w")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(16, 14))
        self.start = ttk.Button(actions, text="开始分离并导出", style="Primary.TButton", command=self.begin)
        self.start.pack(side="left")
        self.stop = ttk.Button(actions, text="取消处理", command=self.cancel_job, state="disabled")
        self.stop.pack(side="left", padx=10)
        self.open_result = ttk.Button(actions, text="打开结果目录", command=self.open_folder, state="disabled")
        self.open_result.pack(side="right")
        self.use_result = ttk.Button(actions, text="将结果用于分离", command=self.use_audio, state="disabled")
        self.use_result.pack(side="right", padx=8)
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill="x", pady=8)
        ttk.Label(frame, textvariable=self.status, wraplength=780).pack(anchor="w", pady=(4, 10))
        self.log = tk.Text(frame, height=6, bg="#101a2e", fg="#d4def6", relief="flat", padx=14, pady=12,
                           font=("Consolas", 9), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)
        ttk.Label(frame, text="分离首次需联网下载模型；转换在本地完成。进度条展示处理阶段，详细进度见日志。\nMP3 码率可选；M4A 为 AAC 256 kbps，OGG 为 Vorbis。", style="Hint.TLabel").pack(anchor="w", pady=(12, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def path_row(self, parent, label, variable, command, button_text, compact=False):
        if not compact:
            ttk.Label(parent, text=label).pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 6 if compact else 14))
        if compact:
            ttk.Label(row, text=label, width=22).pack(side="left")
        entry = ttk.Entry(row, textvariable=variable, font=("Microsoft YaHei UI", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        button = ttk.Button(row, text=button_text, command=command)
        button.pack(side="right", padx=(10, 0))
        self.controls.extend([(entry, "normal"), (button, "normal")])

    def choose_source(self):
        path = filedialog.askopenfilename(title="选择音频文件", filetypes=self.filetypes())
        if path:
            self.source.set(path)

    def filetypes(self):
        encrypted = " ".join("*" + ext for ext in sorted(encrypted_extensions()))
        return [("普通音频", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma *.aiff *.aif *.ape"),
                ("加密音乐", encrypted), ("所有文件", "*.*")]

    def choose_conversion(self):
        paths = filedialog.askopenfilenames(title="选择需要转换的文件", filetypes=self.filetypes())
        if paths:
            self.conversion_sources = [Path(p) for p in paths]
            self.conversion_count.set(f"已选 {len(paths)} 个文件，首个：{Path(paths[0]).name[:35]}")

    def choose_key(self, variable):
        path = filedialog.askopenfilename(title="选择密钥文件")
        if path:
            variable.set(path)

    def update_mode(self):
        if not hasattr(self, "start"):
            return
        mode = self.tabs.index("current")
        self.start.configure(text=["开始分离并导出", "下载并转换音频", "开始批量转换"][mode])
        self.formats.configure(values=["MP3", "WAV", "FLAC", "M4A", "OGG"] + (["保持原格式"] if mode == 2 else []))
        if mode != 2 and self.format.get() == "保持原格式":
            self.format.set("MP3")
        self.update_bitrate()

    def use_audio(self):
        if self.result_audio and self.result_audio.is_file() and not self.busy:
            self.source.set(str(self.result_audio))
            self.tabs.select(0)
            self.status.set("结果已载入，请点击“开始分离并导出”。")

    def choose_destination(self):
        path = filedialog.askdirectory(title="选择导出目录")
        if path:
            self.destination.set(path)

    def update_bitrate(self):
        self.rate.configure(state="readonly" if self.format.get() == "MP3" and not self.busy else "disabled")

    def begin(self):
        if self.busy:
            return
        if not self.destination.get().strip():
            messagebox.showerror("请选择目录", "请先选择导出目录。")
            return
        mode = self.tabs.index("current")
        destination, format, bitrate = Path(self.destination.get()), self.format.get(), self.bitrate.get()
        if format == "保持原格式":
            format = "KEEP"
        key_file = Path(self.key_file.get()) if self.key_file.get().strip() else None
        key_db = Path(self.key_db.get()) if self.key_db.get().strip() else None
        jobs = []
        url = self.url.get().strip()
        try:
            if mode == 0:
                jobs = [Job(Path(self.source.get()), destination, format, bitrate, key_file, key_db)]
                jobs[0].validate()
            elif mode == 1:
                validate_url(url)
            else:
                if not self.conversion_sources:
                    raise ValueError("请先选择一个或多个要转换的文件。")
                jobs = [Job(path, destination, format, bitrate, key_file, key_db) for path in self.conversion_sources]
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        self.busy = True
        self.result = None
        self.result_audio = None
        self.cancel.clear()
        self.progress["value"] = 0
        self.open_result.configure(state="disabled")
        self.use_result.configure(state="disabled")
        self.start.configure(state="disabled")
        self.stop.configure(state="normal")
        for widget, _ in self.controls:
            widget.configure(state="disabled")
        for index in range(3):
            if index != mode:
                self.tabs.tab(index, state="disabled")
        self.append_log("开始任务：" + ["人声伴奏分离", "网上音频下载", "批量格式转换"][mode])

        def worker():
            try:
                log = lambda text: self.events.put(("log", text))
                progress = lambda value, text: self.events.put(("progress", (value, text)))
                if mode == 0:
                    result = separate(jobs[0], self.cancel, log, progress)
                elif mode == 1:
                    result = download_audio(url, destination, format, bitrate, self.cancel, log, progress)
                else:
                    result = convert_files(jobs, self.cancel, log, progress)
                self.events.put(("done", result))
            except Cancelled:
                self.events.put(("cancelled", "已取消，未导出不完整的文件。"))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 350:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.append_log(data)
                elif kind == "progress":
                    self.progress["value"], text = data
                    self.status.set(text)
                else:
                    self.busy = False
                    self.start.configure(state="normal")
                    self.stop.configure(state="disabled")
                    for widget, state in self.controls:
                        widget.configure(state=state)
                    for index in range(3):
                        self.tabs.tab(index, state="normal")
                    self.update_bitrate()
                    if kind == "done":
                        if isinstance(data, ConversionResult):
                            self.result = data.directory
                            self.result_audio = data.files[0]
                            self.use_result.configure(state="normal")
                            message = f"完成：成功 {len(data.files)}，失败 {len(data.failures)}。目录：{self.result}"
                        else:
                            self.result = data
                            message = "完成！原曲、人声、伴奏已保存：" + str(data)
                        self.open_result.configure(state="normal")
                        self.status.set(message)
                        self.append_log(message)
                    elif kind == "cancelled":
                        self.status.set(data)
                        self.progress["value"] = 0
                        self.append_log(data)
                    else:
                        self.status.set("处理失败，请查看日志后重试")
                        self.append_log(data)
                        if not self.closing:
                            messagebox.showerror("处理失败", data + "\n\n首次使用请检查网络；请确认依赖已安装、音频可播放且磁盘空间充足。")
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def cancel_job(self):
        self.cancel.set()
        self.stop.configure(state="disabled")
        self.status.set("正在取消并清理临时文件…")

    def open_folder(self):
        if self.result and self.result.is_dir():
            if os.name == "nt":
                os.startfile(str(self.result))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.result)])

    def close(self):
        if self.busy:
            if messagebox.askyesno("退出", "正在处理音频，取消任务并退出？"):
                self.closing = True
                self.cancel_job()
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
