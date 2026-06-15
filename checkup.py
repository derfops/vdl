import base64
import datetime
import os
import subprocess
import time
from pathlib import Path


def token():
    p = "/data/cookie.txt"
    if os.path.isfile(p):
        b = open(p, "rb").read()
        return base64.b64encode(b).decode("ascii").replace("\n", "")
    return os.environ.get("VDL_TOKEN", "")

def write_env(t):
    Path("/data").mkdir(parents=True, exist_ok=True)
    if t:
        open("/data/vdl_token.env", "w").write(f"export VDL_TOKEN={t}\n")

def log_ip():
    Path("/logs").mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ip = ""
    for _ in range(12):
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "5", "ifconfig.me"], capture_output=True, text=True)
            ip = (r.stdout or "").strip()
        except Exception:
            ip = ""
        if ip:
            break
        time.sleep(5)
    p = f"/logs/{ts}.log"
    open(p, "w").write((ip or "N/A") + "\n")
    return p, ip

def main():
    flag = "/data/.first_start"
    if not os.path.exists(flag):
        time.sleep(30)
        p, ip = log_ip()
        Path(flag).touch()
    else:
        p, ip = log_ip()
    write_env(token())

if __name__ == "__main__":
    main()
