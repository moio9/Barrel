# libs/providers/gog_core/adapters/lgogdownloader.py
from typing import List
from libs.common_core.provider_api import Job, Downloader

class LGOGDownloader(Downloader):
	def build_command(self, job: Job) -> List[str]:
		# exemplu generic; vei adapta la tool-ul ales (lgogdownloader/gogdl)
		# ex: lgogdownloader --game <slug> --download --dir <dest>
		if not job.app_id:
			raise ValueError("GOG: app_id trebuie să fie slug sau product id")
		return ["lgogdownloader", "--game", job.app_id, "--download", "--directory", job.dest_dir]

