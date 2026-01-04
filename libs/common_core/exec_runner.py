import subprocess, threading
from typing import Callable, Optional, List

class EventBus:
    def __init__(self):
        self._on_line: List[Callable[[str], None]] = []
        self._on_exit: List[Callable[[int], None]] = []
    def on_line(self, cb: Callable[[str], None]): self._on_line.append(cb)
    def on_exit(self, cb: Callable[[int], None]): self._on_exit.append(cb)
    def emit_line(self, s: str):
        for cb in self._on_line:
            try: cb(s)
            except: pass
    def emit_exit(self, code: int):
        for cb in self._on_exit:
            try: cb(code)
            except: pass

class ProcessRunner:
    def __init__(self, cmd: List[str], bus: EventBus):
        self.cmd = cmd; self.bus = bus
        self.proc: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
    def start(self):
        def loop():
            try:
                self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    self.bus.emit_line(line)
                self.bus.emit_exit(self.proc.wait())
            except FileNotFoundError:
                self.bus.emit_line(f"[ERR] Tool not found in PATH: {self.cmd[0]}\n"); self.bus.emit_exit(127)
            except Exception as e:
                self.bus.emit_line(f"[ERR] {e}\n"); self.bus.emit_exit(1)
        self.thread = threading.Thread(target=loop, daemon=True); self.thread.start()
    def stop(self):
        if self.proc and self.proc.poll() is None:
            try: self.proc.terminate()
            except: pass

