from dataclasses import dataclass
from typing import Optional, Union, List, Protocol

@dataclass
class Job:
	app_id: Optional[str] = None
	depot_id: Optional[str] = None
	manifest: Optional[str] = None
	branch: Optional[str] = None
	dest_dir: str = ""
	username: Optional[str] = None

	# 🔹 câmpuri noi
	password: Optional[str] = None
	os: Optional[str] = None  # 'windows' sau 'linux'

	remember_password: bool = False
	extra_args: Union[str, List[str], None] = None

class Downloader(Protocol):
    def build_command(self, job: Job) -> List[str]: ...

class Provider(Protocol):
    def resolve_job(self, job: Job) -> Job: ...
    def get_downloader(self, tool: Optional[str] = None) -> Downloader: ...

