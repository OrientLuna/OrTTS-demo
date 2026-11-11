"""python3 -m linux.app --library /path/to/libortts.so"""
import argparse
from pathlib import Path
import tkinter as tk

from desktop.app import App
from linux.audio import StreamPlayer


def main():
    parser = argparse.ArgumentParser(description="OrTTS Linux 桌面 Demo")
    parser.add_argument("--library", type=Path, help="原生 libortts.so")
    parser.add_argument("--state-dir", type=Path, help="独立用户数据目录")
    parser.add_argument("--audio-device", help="可选 ALSA 设备；null 仅供无声自动化验证")
    args = parser.parse_args()
    root = tk.Tk()
    app = App(root, args.library, args.state_dir, stream_player=StreamPlayer(args.audio_device))
    root.mainloop()


if __name__ == "__main__":
    main()
