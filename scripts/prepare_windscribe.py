from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "Windscribe-StaticIP-WG.conf"
TARGET_DIR = ROOT / "windscribe"
TARGET_PATH = TARGET_DIR / "wg0.conf"


def main() -> int:
    if not SOURCE_PATH.exists():
        print(f"Arquivo nao encontrado: {SOURCE_PATH}")
        return 1

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_PATH.write_text(_normalize_config(SOURCE_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    TARGET_PATH.chmod(0o600)
    print(f"Windscribe WireGuard pronto em: {TARGET_PATH}")
    return 0


def _normalize_config(config: str) -> str:
    lines = []
    for line in config.splitlines():
        key, separator, value = line.partition("=")
        normalized_key = key.strip()
        if separator and normalized_key in {"Address", "AllowedIPs"}:
            values = [item.strip() for item in value.split(",")]
            ipv4_values = [item for item in values if ":" not in item]
            line = f"{normalized_key} = {', '.join(ipv4_values)}"
        lines.append(line)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
