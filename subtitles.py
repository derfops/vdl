#!/usr/bin/env python3
"""
subtitles.py ─ Gerador de legendas automáticas + tradução pt‑BR (Plex‑ready)
===============================================================================
• Transcrição OpenAI‑Whisper (modelo tiny por default)
• Tradução via OpenAI Chat API (SDK >=1.0)
• Corrige overlaps (≥3 ms) e remove backticks/aspas da tradução
• Grava UTF-8:  <video>.<idioma_origem>.srt  e  <video>.<args.lang>.srt

CONFIGURAÇÕES RÁPIDAS – edite aqui ou passe por CLI
"""
# ───────── Config section ─────────
TARGET_LANGUAGE_CODE      = "pt-BR"   # extensão do SRT traduzido (--lang)
DEFAULT_SLEEP_BETWEEN_API = 1.0       # segundos entre chamadas OpenAI (--sleep)
# ───────────────────────────────────

import argparse
import gc
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

MEDIA_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".mp3", ".wav"}

# ───────────── Helpers de tempo / SRT ─────────────
def sec_to_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def fix_segments(raw: List[Dict[str, Any]], delta: float = 0.003):
    """Folga mínima de 3 ms depois do arredondamento."""
    last_end = -delta
    for s in raw:
        if s["start"] - last_end < delta:
            s["start"] = last_end + delta
        if s["end"] - s["start"] < delta:
            s["end"] = s["start"] + delta
        s["start"] = round(s["start"], 3)
        s["end"]   = round(s["end"],   3)
        last_end = s["end"]
    return raw

def to_srt(segs: List[Dict[str, Any]]) -> str:
    out = []
    for i, s in enumerate(segs, 1):
        out += [
            str(i),
            f"{sec_to_ts(s['start'])} --> {sec_to_ts(s['end'])}",
            s["text"].strip(),
            ""
        ]
    out.append("")  # linha em branco final
    return "\n".join(out)

def write_utf8(path: Path, text: str):
    with path.open("w", encoding="utf-8") as f:
        f.write(text)

# ───────────── I/O helpers ─────────────
def extract_audio(video: Path) -> Path:
    tmp = Path(tempfile.gettempdir()) / f"{video.stem}_{int(time.time())}.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
         "-ac", "1", "-ar", "16000", "-vn", str(tmp)],
        check=True
    )
    return tmp

def sanitize_line(t: str) -> str:
    """Remove backticks e aspas duplas/curvas nas pontas."""
    t = t.strip()
    if (t.startswith(("`", '"', "“")) and t.endswith(("`", '"', "”")) and len(t) > 1):
        t = t[1:-1].strip()
    return t.replace("`", "").replace("“", "").replace("”", "")

# ───────────── Tradução ─────────────
def translate(texts: List[str], engine: str, lang: str,
              sleep_s: float, source_lang: str = "en") -> List[str]:
    if engine == "none":
        return texts

    if engine == "google":
        from googletrans import Translator
        iso = lang.split("-")[0].lower()
        if iso == "pt-BR":   # google não reconhece "pt-BR"
            iso = "pt"
        translated = Translator().translate(texts, dest=iso)
        return [sanitize_line(t.text) for t in translated]

    if engine == "openai":
        # Pinamos SDK >=1.0 em requirements; sem branch legado.
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        def chat_completion(messages):
            return client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            ).choices[0].message.content

        guideline = (
            f"You translate subtitle lines from {source_lang.upper()} to "
            f"{lang.upper()} (Português do Brasil). "
            "Do NOT translate technical terms, cloud service names, commands, "
            "error codes, words fully in UPPERCASE, or any text inside backticks. "
            "Return ONLY a JSON object: {\"translations\": [\"line 1\", \"line 2\", ...]} "
            "preserving the exact same number of lines as the input array, in the same order. "
            "Each translation must be plain text, no quotes/backticks, single line."
        )

        CHUNK = 20
        out: List[str] = []
        for i in range(0, len(texts), CHUNK):
            chunk = texts[i:i+CHUNK]
            user_payload = {"lines": chunk}
            messages = [
                {"role": "system", "content": guideline},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ]
            content = chat_completion(messages)
            try:
                parsed = json.loads(content)
                translations = parsed.get("translations", [])
                if not isinstance(translations, list):
                    raise ValueError("translations não é lista")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"   ! JSON inválido na resposta de tradução ({e}); usando original")
                translations = chunk[:]
            # Garantir tamanho correto sem dessincronizar
            if len(translations) < len(chunk):
                translations = translations + [""] * (len(chunk) - len(translations))
            elif len(translations) > len(chunk):
                translations = translations[:len(chunk)]
            translations = [sanitize_line(str(t)) for t in translations]
            out.extend(translations)
            time.sleep(sleep_s)
        return out

    raise ValueError("engine de tradução inválido")

# ───────────── Processa um vídeo ─────────────
def process_file(model, vid: Path, args):
    print(f"▶  {vid.name}")
    audio = extract_audio(vid)
    try:
        res = model.transcribe(str(audio), verbose=False)
        # Usa o idioma detectado pelo Whisper para nomear a legenda source.
        # (antes era hardcoded "en", causando arquivos .en.srt com PT/ES/etc.)
        detected_lang = res.get("language") or "und"
        # ISO codes do whisper são 2 chars (en, pt, es...). Mapeamos pt -> pt para Plex,
        # mas mantemos o detectado quando disponível.
        source_code = detected_lang
        source_srt = vid.with_suffix(f".{source_code}.srt")
        target_srt = vid.with_suffix(f".{args.lang}.srt")

        if not args.overwrite and source_srt.exists() and target_srt.exists():
            print(f"   • legendas já existem ({source_code}+{args.lang}), pulando")
            return

        segs = fix_segments([{k: s[k] for k in ("start", "end", "text")}
                             for s in res["segments"]])

        write_utf8(source_srt, to_srt(segs))

        # Se source == target (áudio já em pt-BR e queremos pt-BR), pula tradução
        if source_code.lower() == args.lang.lower().split("-")[0]:
            print(f"   • áudio já em {source_code}, sem tradução")
            return

        try:
            translated = translate([s["text"] for s in segs],
                                   args.translate_engine, args.lang, args.sleep,
                                   source_lang=source_code)
            segs_pt = [{**s, "text": t} for s, t in zip(segs, translated)]
            write_utf8(target_srt, to_srt(segs_pt))
            print(f"   • OK ({source_code} + {args.lang})")
        except Exception as e:
            print(f"   ! Tradução falhou ({e}) – gerado apenas {source_code}")
    finally:
        audio.unlink(missing_ok=True)
        gc.collect()

# ───────────── CLI / main ─────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="Arquivo ou diretório com mídia")
    ap.add_argument("--model", default="tiny",
                    help="Modelo Whisper (tiny|base|small|medium|large)")
    ap.add_argument("--device", default="cpu", help="cpu|cuda")
    ap.add_argument("--translate-engine", default="openai",
                    choices=["openai", "google", "none"])
    ap.add_argument("--lang", default=TARGET_LANGUAGE_CODE,
                    help="Extensão da legenda traduzida (pt-BR = pt‑BR)")
    ap.add_argument("--overwrite", action="store_true",
                    help="Recria SRT mesmo se já existir")
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_BETWEEN_API,
                    help="Delay entre chamadas OpenAI (segundos)")
    ap.add_argument("--threads", type=int, default=0,
                    help="Threads do torch (0=padrão do sistema, recomendado para CPU multi-core).")
    args = ap.parse_args()

    import torch
    if args.threads > 0:
        torch.set_num_threads(args.threads)

    # Reaproveita o helper compartilhado para garantir comportamento consistente
    # com o vdl.py (cache de modelo via VDL_WHISPER_CACHE, etc.).
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _transcription import load_whisper_model

    print(f"╭─ Carregando modelo {args.model}…")
    use_gpu = args.device == "cuda"
    model, _device = load_whisper_model(args.model, use_gpu=use_gpu)
    print("╰─ Modelo pronto.\n")

    root = Path(args.target)
    vids = [root] if root.is_file() else [
        f for f in root.rglob("*") if f.suffix.lower() in MEDIA_EXT]

    if not vids:
        sys.exit("Nada a processar.")

    for v in sorted(vids):
        try:
            process_file(model, v, args)
        except Exception as exc:
            print(f"   ! Erro inesperado: {exc}")

if __name__ == "__main__":
    main()