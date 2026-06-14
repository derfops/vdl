from __future__ import annotations

import socket
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = ROOT / "glutenn_openvpn.zip"
GLUETUN_DIR = ROOT / "gluetun"
OVPN_PATH = GLUETUN_DIR / "openvpn.ovpn"


def main() -> int:
    if not ZIP_PATH.exists():
        print(f"Arquivo nao encontrado: {ZIP_PATH}")
        return 1

    GLUETUN_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH) as archive:
        archive.extractall(GLUETUN_DIR)

    lines = OVPN_PATH.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        parts = line.split()
        if parts and parts[0] == "redirect-gateway":
            continue
        if len(parts) >= 3 and parts[0] == "remote":
            host, port = parts[1], parts[2]
            ip = _resolve_first_ipv4(host)
            if ip:
                line = f"remote {ip} {port}"
        elif len(parts) == 2 and parts[0] in {"ca", "cert", "key"}:
            line = f"{parts[0]} /gluetun/{Path(parts[1]).name}"
        updated.append(line)

    OVPN_PATH.write_text("\n".join(updated) + "\n", encoding="utf-8")
    key_path = GLUETUN_DIR / "client.key"
    if key_path.exists():
        key_path.chmod(0o600)
    print(f"Gluetun OpenVPN pronto em: {GLUETUN_DIR}")
    return 0


def _resolve_first_ipv4(host: str) -> str | None:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    for info in infos:
        ip = info[4][0]
        if ":" not in ip:
            return ip
    return None


if __name__ == "__main__":
    raise SystemExit(main())
