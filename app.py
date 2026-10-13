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


class App:
    def __init__(self, root):
        self.root = root
        root.title("声伴 · 音频分离工作室")
        root.geometry("880x720")
        root.minsize(760, 650)
        root.configure(bg="#f4f6fb")
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.result = None
        self.source = tk.StringVar()
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
        frame = ttk.Frame(root, padding=28)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="声伴 Sound Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="让人声与伴奏各自精彩 · 本地处理，三份音频一次导出", style="Hint.TLabel").pack(anchor="w", pady=(4, 22))
        self.controls = []
        self.path_row(frame, "01  选择音频", self.source, self.choose_source, "浏览音频")
        self.path_row(frame, "02  保存到", self.destination, self.choose_destination, "选择目录")
        options = ttk.Frame(frame)
        options.pack(fill="x", pady=(10, 20))
        ttk.Label(options, text="03  导出格式").pack(side="left")
        formats = ttk.Combobox(options, textvariable=self.format, values=["MP3", "WAV", "FLAC"], width=9, state="readonly")
        formats.pack(side="left", padx=12)
        formats.bind("<<ComboboxSelected>>", lambda _: self.update_bitrate())
        self.controls.append((formats, "readonly"))
        ttk.Label(options, text="MP3 码率").pack(side="left", padx=(14, 0))
        self.rate = ttk.Combobox(options, textvariable=self.bitrate, values=["128", "192", "256", "320"], width=7, state="readonly")
        self.rate.pack(side="left", padx=12)
        ttk.Label(options, text="kbps", style="Hint.TLabel").pack(side="left")
        self.controls.append((self.rate, "readonly"))
        ttk.Label(frame, text="输出：original 原曲  /  vocals 人声  /  accompaniment 伴奏", style="Hint.TLabel").pack(anchor="w")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(16, 14))
        self.start = ttk.Button(actions, text="开始分离并导出", style="Primary.TButton", command=self.begin)
        self.start.pack(side="left")
        self.stop = ttk.Button(actions, text="取消处理", command=self.cancel_job, state="disabled")
        self.stop.pack(side="left", padx=10)
        self.open_result = ttk.Button(actions, text="打开结果目录", command=self.open_folder, state="disabled")
        self.open_result.pack(side="right")
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill="x", pady=8)
        ttk.Label(frame, textvariable=self.status, wraplength=780).pack(anchor="w", pady=(4, 10))
        self.log = tk.Text(frame, height=10, bg="#101a2e", fg="#d4def6", relief="flat", padx=14, pady=12,
                           font=("Consolas", 9), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)
        ttk.Label(frame, text="支持 MP3 / WAV / FLAC / M4A 等。首次下载模型需联网，CPU 分离可能耗时数分钟。\n进度条展示处理阶段；分离可能有残留声，结果取决于原始音频。", style="Hint.TLabel").pack(anchor="w", pady=(12, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def path_row(self, parent, label, variable, command, button_text):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 14))
        entry = ttk.Entry(row, textvariable=variable, font=("Microsoft YaHei UI", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        button = ttk.Button(row, text=button_text, command=command)
        button.pack(side="right", padx=(10, 0))
        self.controls.extend([(entry, "normal"), (button, "normal")])

    def choose_source(self):
        path = filedialog.askopenfilename(title="选择音频文件", filetypes=[("音频", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma *.aiff *.aif"), ("所有文件", "*.*")])
        if path:
            self.source.set(path)

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
        job = Job(Path(self.source.get()), Path(self.destination.get()), self.format.get(), self.bitrate.get())
        try:
            job.validate()
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        self.busy = True
        self.result = None
        self.cancel.clear()
        self.progress["value"] = 0
        self.open_result.configure(state="disabled")
        self.start.configure(state="disabled")
        self.stop.configure(state="normal")
        for widget, _ in self.controls:
            widget.configure(state="disabled")
        self.append_log("开始处理：" + str(job.source))

        def worker():
            try:
                result = separate(job, self.cancel, lambda text: self.events.put(("log", text)),
                                  lambda value, text: self.events.put(("progress", (value, text))))
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
                    self.update_bitrate()
                    if kind == "done":
                        self.result = data
                        self.open_result.configure(state="normal")
                        self.status.set("完成！已保存三份音频：" + str(data))
                        self.append_log("完成：" + str(data))
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
