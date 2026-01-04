from typing import List
from libs.common_core.provider_api import Job

def build_args(job: Job) -> List[str]:
    """
    Construiește lista de argumente pentru DepotDownloader.
    """
    cmd = ["depotdownloader", "-depot", job.depot_id, "-dir", job.dest_dir]
    
    if job.app_id:
        # -app trebuie să fie prezent pentru unele depouri
        cmd[1:1] = ["-app", job.app_id]
    if job.branch:
        cmd += ["-beta", job.branch]
    if job.manifest:
        cmd += ["-manifest", job.manifest]
    if job.username:
        cmd += ["-username", job.username]
    if getattr(job, "password", None):
        cmd += ["-password", job.password]
    if getattr(job, "os", None):
        cmd += ["-os", job.os]
    if job.remember_password:
        cmd += ["-remember-password"]
    if job.extra_args:
        # dacă extra_args e string
        if isinstance(job.extra_args, str):
            cmd += job.extra_args.split()
        else:
            cmd += job.extra_args

    return cmd

