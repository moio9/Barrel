from typing import List
from libs.common_core.provider_api import Job

def build_args(job: Job) -> List[str]:
    """
    Construiește lista de argumente pentru steam-cli (steamctl).
    """
    cmd = ["steam-cli", "depot", "download", job.depot_id, "--dir", job.dest_dir]
    if job.manifest:
        cmd += ["--manifest", job.manifest]
    if job.extra_args:
        cmd += job.extra_args.split()
    return cmd

