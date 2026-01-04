# libs/providers/steam_core/download_service.py
import os
import subprocess
import threading
import shlex

class SteamDownloadService:
	def __init__(self, event_bus):
		self.bus = event_bus
		self._proc = None
		self._reader_thread = None
		self._stop_flag = False

	def start(self, job, tool="depotdownloader"):
		"""
		job:
		  - app_id: str|None
		  - depot_id: str|None
		  - manifest: str|None
		  - branch: str|None
		  - dest_dir: str
		  - username: str|None
		  - remember_password: bool
		  - extra_args: list[str]|None
		"""
		# oprește rularea anterioară, dacă există
		if self._proc is not None:
			self.stop()

		# construiește comanda
		cmd = self._build_args(job, tool)
		env = os.environ.copy()

		# asigură directorul destinație
		if job.dest_dir and not os.path.isdir(job.dest_dir):
			os.makedirs(job.dest_dir, exist_ok=True)

		# log comanda (vizibil în UI)
		self._emit("line", "[i] Running: " + " ".join(_redact_cmd(cmd)) + "\n")

		exe = cmd[0]
		if os.path.sep in exe:
		    exists = os.path.isfile(exe) and os.access(exe, os.X_OK)
		else:
		    exists = _which(exe) is not None

		if not exists:
		    self._emit("line", f"[!] Executabilul '{exe}' nu a fost găsit sau nu este executabil.\n")
		    self._emit("exit", 127)
		    return

		# pornește procesul O SINGURĂ DATĂ
		self._stop_flag = False
		try:
			self._proc = subprocess.Popen(
				cmd,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				cwd=job.dest_dir or None,
				text=True,
				bufsize=1,
				env=env,
			)
		except Exception as e:
			self._emit("line", f"[!] Eroare la pornire: {e}\n")
			self._emit("exit", 1)
			self._proc = None
			return

		if not self._proc or not self._proc.stdout:
			self._emit("line", "[!] Nu pot capta stdout-ul procesului.\n")
			self._emit("exit", 1)
			return

		# ✅ capturează obiectul proces pentru thread (evită race cu stop())
		proc = self._proc

		def _pump(proc=proc):
			try:
				for line in iter(proc.stdout.readline, ''):
					if self._stop_flag:
						break
					if line:
						self._emit("line", line)
			except Exception as e:
				self._emit("line", f"[!] Reader error: {e}\n")
			finally:
				try:
					code = proc.wait()
				except Exception:
					code = -1
				self._emit("exit", code)
				if self._proc is proc:
					self._proc = None
	
		self._reader_thread = threading.Thread(target=_pump, daemon=True)
		self._reader_thread.start()

	def stop(self):
		self._stop_flag = True
		proc = self._proc
		if proc and proc.poll() is None:
			try:
				proc.terminate()
			except Exception:
				pass
			try:
				proc.wait(timeout=3)
			except Exception:
				pass
		# marchează că nu mai avem proces activ
		self._proc = None

		# încearcă să oprești frumos thread-ul de citire
		t = self._reader_thread
		if t and t.is_alive():
			try:
				t.join(timeout=1)
			except Exception:
				pass

	# -------------------------
	# Internals
	# -------------------------
	def _build_args(self, job, tool):
		tool = (tool or "depotdownloader").strip().lower()

		if tool in ("depotdownloader", "dd", "depot"):
			return self._build_depotdownloader(job)
		elif tool in ("steam-cli", "steamcmd", "steam"):
			return self._build_steamcmd(job)
		else:
			# fallback: depotdownloader
			return self._build_depotdownloader(job)

	def _build_depotdownloader(self, job):
		"""
		Suportă 2 moduri:
		1) Binar nativ:  'depotdownloader ...'   (Termux / pachete)
		2) .NET DLL:     'dotnet DepotDownloader.dll ...'  (fallback)
		Poți forța binarul sau dll-ul cu env:
		  DEPOTDOWNLOADER_BIN=/cale/depotdownloader
		  DEPOTDOWNLOADER_DLL=/cale/DepotDownloader.dll
		"""
		# 1) Preferă binarul nativ, dacă există
		bin_candidates = []
		if "DEPOTDOWNLOADER_BIN" in os.environ:
			bin_candidates.append(os.environ["DEPOTDOWNLOADER_BIN"])
		bin_candidates += ["depotdownloader", "/data/data/com.termux/files/usr/bin/depotdownloader"]

		bin_path = next((p for p in bin_candidates if _which(os.path.basename(p)) or os.path.isfile(p)), None)
		if bin_path and (_which(os.path.basename(bin_path)) or os.path.isfile(bin_path)):
			cmd = [bin_path]
		else:
			# 2) Fallback la DLL .NET
			dll_candidates = []
			home = os.path.expanduser("~")
			if "DEPOTDOWNLOADER_DLL" in os.environ:
				dll_candidates.append(os.environ["DEPOTDOWNLOADER_DLL"])
			dll_candidates += [
				os.path.join(home, "DepotDownloader", "DepotDownloader.dll"),
				os.path.join(home, "Apps", "DepotDownloader", "DepotDownloader.dll"),
				"DepotDownloader.dll",
			]
			dll = next((p for p in dll_candidates if os.path.isfile(p)), "DepotDownloader.dll")
			cmd = ["dotnet", dll]

		# Argumente comune
		def add(arg, val=None):
			if val is None:
				cmd.append(arg)
			else:
				cmd.extend([arg, str(val)])

		if getattr(job, "app_id", None):      add("-app", job.app_id)
		if getattr(job, "depot_id", None):    add("-depot", job.depot_id)
		if getattr(job, "manifest", None):    add("-manifest", job.manifest)
		if getattr(job, "branch", None):      add("-beta", job.branch)
		if getattr(job, "username", None):    add("-username", job.username)
		if getattr(job, "password", None):    add("-password", job.password)   # ← nou
		if getattr(job, "os", None):          add("-os", job.os)               # ← nou
		if getattr(job, "remember_password", False): add("-remember-password")
		if getattr(job, "dest_dir", None):    add("-dir", job.dest_dir)

		# Extra args (acceptă listă sau string)
		ea = getattr(job, "extra_args", None)
		if ea:
			if isinstance(ea, str):
				cmd += shlex.split(ea)
			else:
				cmd += [str(a) for a in ea]

		return cmd


	def _build_steamcmd(self, job):
		steamcmd = "steamcmd"
		if not _which(steamcmd):
			steamcmd = "steamcmd.sh"

		script = []

		# login
		if getattr(job, "username", None):
			if getattr(job, "password", None):
				script.append(f'+login {_quote(job.username)} {_quote(job.password)}')
			else:
				script.append(f'+login {_quote(job.username)}')
		else:
			script.append('+login anonymous')

		# app update (cu/ fără beta)
		if getattr(job, "app_id", None):
			if getattr(job, "branch", None):
				script.append(f'+app_update {job.app_id} -beta {_quote(job.branch)} validate')
			else:
				script.append(f'+app_update {job.app_id} validate')

		# download_depot opțional
		if getattr(job, "depot_id", None):
			if getattr(job, "manifest", None):
				script.append(f'+download_depot {job.app_id} {job.depot_id} {job.manifest}')
			else:
				script.append(f'+download_depot {job.app_id} {job.depot_id}')

		script.append('+quit')

		return [steamcmd] + script

	def _emit(self, kind, payload):
		if kind == "line":
			for name in ("emit_line", "publish_line", "push_line", "send_line"):
				if hasattr(self.bus, name):
					getattr(self.bus, name)(payload); return
		elif kind == "exit":
			for name in ("emit_exit", "publish_exit", "push_exit", "send_exit"):
				if hasattr(self.bus, name):
					getattr(self.bus, name)(payload); return
		# fallback: emit generic
		if hasattr(self.bus, "emit"):
			self.bus.emit(kind, payload)
		# fallback final: apelează liste de callbackuri, dacă există
		elif hasattr(self.bus, "on_line_callbacks") and kind == "line":
			for cb in getattr(self.bus, "on_line_callbacks"):
				try: cb(payload)
				except: pass
		elif hasattr(self.bus, "on_exit_callbacks") and kind == "exit":
			for cb in getattr(self.bus, "on_exit_callbacks"):
				try: cb(payload)
				except: pass

def _which(prog):
	for p in os.environ.get("PATH", "").split(os.pathsep):
		full = os.path.join(p, prog)
		if os.path.isfile(full) and os.access(full, os.X_OK):
			return full
	return None

def _quote(s):
	return shlex.quote(str(s))
	
def _redact_cmd(cmd_list):
	safe = []
	for tok in cmd_list:
		# Redactează steamcmd: "+login user pass" -> "+login user ********"
		if tok.startswith("+login "):
			parts = tok.split(" ")
			if len(parts) >= 3:
				parts[-1] = "********"
			safe.append(" ".join(parts))
			continue
		safe.append(tok)

	# Redactează DepotDownloader: "-password", valoarea următoare
	for i in range(len(safe) - 1):
		if safe[i].lower() in ("-password", "--password"):
			safe[i+1] = "********"
	return safe

