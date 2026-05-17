#!/usr/bin/env python3
import argparse
import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

# Regex compilada para limpar ANSI escape codes (CSI sequences) do output do
# yt-dlp ao gravar no arquivo de log. Cobre ESC[...m, ESC[...K, etc.
_ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# --- Variável Global para o Arquivo de Log ---
LOG_FILE = None

# --- Funções de Cores ---
C_RED = '\033[91m'
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_BLUE = '\033[94m'
C_END = '\033[0m'

# --- Funções de Impressão Modificadas para Logging ---
def print_to_console_and_log(message, color=""):
    """Função central que imprime na tela e opcionalmente no arquivo de log.

    No log gravamos a versão plana: removemos cores próprias e ANSI escape
    codes vindos do yt-dlp (que polui o log com sequências [0m, [K, etc.)."""
    plain_message = message
    for code in [C_RED, C_GREEN, C_YELLOW, C_BLUE, C_END]:
        plain_message = plain_message.replace(code, "")
    plain_message = _ANSI_ESCAPE_RE.sub("", plain_message)

    print(f"{color}{message}{C_END}")

    if LOG_FILE:
        LOG_FILE.write(plain_message + "\n")
        LOG_FILE.flush()

def print_error(message):
    print_to_console_and_log(f"[ERRO] {message}", C_RED)

def print_info(message):
    print_to_console_and_log(f"[INFO] {message}", C_BLUE)

def print_success(message):
    print_to_console_and_log(f"[SUCESSO] {message}", C_GREEN)

# --- Helpers de prompts externos ---
def _load_prompt_template(name):
    """Carrega template de prompt do diretório prompts/ ao lado do script.
    Retorna string com placeholders Python ({var})."""
    prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    path = os.path.join(prompts_dir, name)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# --- Helpers de retry (OpenAI) ---
def _retry_with_backoff(fn, *args, max_attempts=4, base_delay=2.0, op_name="operação", **kwargs):
    """Executa fn(*args, **kwargs) com retry exponencial + jitter para falhas
    transitórias da API OpenAI (rate limit, 5xx, conexão). Levanta a última
    exceção se todas as tentativas falharem."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            err_text = str(e).lower()
            transient = any(s in err_text for s in (
                "rate limit", "ratelimit", "timeout", "connection", "5xx",
                "service unavailable", "overloaded", "internal server", "503", "502", "504",
            ))
            if not transient or attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print_to_console_and_log(
                f"[AVISO] Falha transitória em {op_name} (tentativa {attempt}/{max_attempts}): {e}. "
                f"Tentando novamente em {delay:.1f}s...",
                C_YELLOW,
            )
            time.sleep(delay)


# --- Funções de Setup e Verificação ---
def setup_logging():
    """Configura o logging automaticamente.

    Inclui microssegundos e PID no nome do arquivo para evitar colisão entre
    invocações paralelas (ex.: pipeline Jenkins disparando múltiplos vdl ao
    mesmo tempo)."""
    global LOG_FILE
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    log_filename = os.path.join(log_dir, f"{timestamp}_pid{os.getpid()}.log")
    try:
        LOG_FILE = open(log_filename, 'w', encoding='utf-8')
        print_info(f"Logging ativado. A saída será salva em: {log_filename}")
    except IOError as e:
        print_error(f"Não foi possível criar o arquivo de log: {e}")
        LOG_FILE = None

def check_dependencies(args):
    """Verifica as dependências com base nos argumentos fornecidos."""
    has_error = False
    # Apenas verifica yt-dlp se não estiver em modo local
    if not args.local and not shutil.which("yt-dlp"):
        print_error("Dependência não encontrada: 'yt-dlp'. Instale-a.")
        has_error = True

    # ffmpeg é necessário para quase tudo, exceto --only-download
    if not args.only_download and not shutil.which("ffmpeg"):
        print_error("Dependência não encontrada: 'ffmpeg'. Instale-a.")
        has_error = True

    if args.transcribe and not args.unified_mode:
        try: import whisper
        except ImportError:
            print_error("Dependência para transcrição local não encontrada: 'openai-whisper'. Use: pip install openai-whisper")
            has_error = True

    if args.context or args.unified_mode:
        try: import openai
        except ImportError:
            print_error("Dependência para a API OpenAI não encontrada: 'openai'. Use: pip install openai")
            has_error = True
        try: import pydub
        except ImportError:
            print_error("Dependência para manipulação de áudio não encontrada: 'pydub'. Use: pip install pydub")
            has_error = True
        if not os.getenv("OPENAI_API_KEY"):
            print_error("A variável de ambiente OPENAI_API_KEY não está definida.")
            has_error = True

    return not has_error

def get_auth_details():
    """Obtém detalhes de autenticação de VDL_TOKEN (Base64) ou arquivos de cookies.

    Retorna (user_agent, cookie_header, referer, cookies_list).
    - cookies_list é a lista crua de cookies em JSON (quando disponível),
      usada para gerar arquivo Netscape para yt-dlp via --cookies.
    - Quando cookies_list é None, o yt-dlp usa cookie_header via header
      (caminho legado, com avisos de segurança e escopo de domínio).
    """
    vdl_token_b64 = os.getenv("VDL_TOKEN")
    if vdl_token_b64:
        # Strip whitespace/newlines que podem vir de heredoc, CLI multiline ou .env files
        vdl_token_b64 = vdl_token_b64.strip()
        print_info("Usando autenticação via variável de ambiente VDL_TOKEN (Base64).")
        try:
            decoded_token = base64.b64decode(vdl_token_b64).decode('utf-8')

            # Verifica se é o formato tradicional com separador ';'
            if ';' in decoded_token and not decoded_token.strip().startswith('['):
                print_to_console_and_log(
                    "[AVISO] Formato 'UA;cookie' está deprecado. User-Agents reais "
                    "contêm ';' que quebra o parser. Use cookies em JSON.",
                    C_YELLOW,
                )
                user_agent, cookie_value = decoded_token.split(';', 1)
                return user_agent, cookie_value, None, None

            # Se não tem ';', verifica se é um JSON de cookies
            elif decoded_token.strip().startswith('[') and decoded_token.strip().endswith(']'):
                print_info("VDL_TOKEN contém cookies JSON. Processando automaticamente...")
                result = _extract_cookies_universal(decoded_token)
                if result:
                    user_agent, cookie_header, referer, cookies_list = result
                    print_info("Cookies extraídos com sucesso do VDL_TOKEN.")
                    return user_agent, cookie_header, referer, cookies_list
                else:
                    print_error("Falha ao processar cookies JSON do VDL_TOKEN.")
                    return None, None, None, None

            # Se não é nem formato tradicional nem JSON, tenta como fallback
            else:
                print_error("VDL_TOKEN decodificado não contém ';' como separador nem é JSON válido.")
                return _try_process_cookies_automatically()

        except (base64.binascii.Error, ValueError, UnicodeDecodeError) as e:
            print_error(f"Formato inválido ou erro na decodificação de VDL_TOKEN. Erro: {e}")
            return _try_process_cookies_automatically()
    else:
        print_info("VDL_TOKEN não encontrada. Tentando ler arquivos de cookies.")
        return _try_process_cookies_automatically()

def _try_process_cookies_automatically():
    """Tenta processar cookies de diferentes formatos automaticamente.

    Retorna (user_agent, cookie_header, referer, cookies_list) ou tupla com Nones.
    Procura nos seguintes locais (em ordem):
    1. CWD (cookies.json, cookie.json, cookies.txt, cookie.txt, token.txt)
    2. Diretório do script (mesma lista)
    """
    cookie_filenames = ['cookies.json', 'cookie.json', 'cookies.txt', 'cookie.txt', 'token.txt']
    search_dirs = [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]
    # Remove duplicatas mantendo ordem
    seen = set()
    search_dirs = [d for d in search_dirs if not (d in seen or seen.add(d))]

    candidates = []
    for d in search_dirs:
        for fname in cookie_filenames:
            candidates.append(os.path.join(d, fname))

    for cookie_file in candidates:
        if os.path.exists(cookie_file):
            print_info(f"Tentando processar arquivo de cookies: {cookie_file}")
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()

                # Tenta processar como cookies exportados do navegador (JSON array)
                if content.startswith('[') and content.endswith(']'):
                    result = _extract_cookies_universal(content)
                    if result:
                        user_agent, cookie_header, referer, cookies_list = result
                        print_info(f"Cookies processados com sucesso de {cookie_file}")
                        return user_agent, cookie_header, referer, cookies_list

                # Tenta processar como formato antigo (cookie.txt)
                else:
                    data = json.loads(content)
                    if 'userAgent' in data:
                        user_agent = data['userAgent']
                        # Procura por diferentes estruturas de domínio
                        for domain_key in data.keys():
                            if domain_key.startswith('.') and isinstance(data[domain_key], dict):
                                for subdomain in data[domain_key].values():
                                    if isinstance(subdomain, dict) and 'aws-waf-token' in subdomain:
                                        cookie_value = f"aws-waf-token={subdomain['aws-waf-token']['value']}"
                                        referer = f"https://{domain_key.lstrip('.')}/"
                                        print_info(f"Autenticação extraída de {cookie_file} (formato antigo)")
                                        return user_agent, cookie_value, referer, None

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                continue

    print_error("Falha ao processar cookies. Métodos suportados:")
    print_error("1. Variável VDL_TOKEN (cookies JSON em Base64; formato 'UA;cookie' está deprecado)")
    print_error("2. Arquivo cookies.json com cookies exportados do navegador")
    print_error("3. Arquivo token.txt no diretório do script ou CWD")
    return None, None, None, None

def _extract_cookies_universal(cookies_data):
    """
    Sistema universal de extração de cookies que detecta automaticamente padrões
    de autenticação e processa qualquer formato de cookie, independente da plataforma.

    Retorna (user_agent, cookie_header, referer, cookies_list).
    - referer é inferido do campo 'domain' do cookie de autenticação mais relevante
      e é útil para acessar streams hospedados em CDNs (BunnyCDN, Cloudflare, etc.)
      que protegem o conteúdo via hot-link/Referer da plataforma original.
    - cookies_list é a lista crua dos cookies (JSON parsed), permitindo gerar
      arquivo Netscape para passar ao yt-dlp via --cookies (escopo correto de domínio).
    """
    # User-Agent padrão (definido no início para estar disponível em todo o escopo)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def _domain_to_referer(domain):
        if not domain:
            return None
        return f"https://{domain.lstrip('.')}/"

    try:
        cookies_list = json.loads(cookies_data)
        if not isinstance(cookies_list, list):
            return None

        # Estratégia 1: Detecta tokens divididos (padrão comum em NextAuth e similares)
        session_tokens = {}
        session_token_domains = {}
        for cookie in cookies_list:
            if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
                name = cookie['name']
                value = cookie['value']

                # Procura por tokens divididos com padrão: nome.numero
                if '.session-token.' in name or '-session.' in name:
                    # Extrai o número da parte
                    parts = name.split('.')
                    if len(parts) >= 2 and parts[-1].isdigit():
                        part_num = parts[-1]
                        base_name = '.'.join(parts[:-1])
                        if base_name not in session_tokens:
                            session_tokens[base_name] = {}
                        session_tokens[base_name][part_num] = value
                        session_token_domains.setdefault(base_name, cookie.get('domain'))

        # Se encontrou tokens divididos, concatena e retorna
        for base_name, parts in session_tokens.items():
            if parts:
                sorted_parts = sorted(parts.keys())
                concatenated_token = ''.join(parts[part] for part in sorted_parts)
                cookie_header = f"{base_name}={concatenated_token}"
                referer = _domain_to_referer(session_token_domains.get(base_name))
                print_info(f"Token dividido detectado: {base_name} ({len(sorted_parts)} parte(s))")
                return user_agent, cookie_header, referer, cookies_list

        # Estratégia 2: Procura por cookies de autenticação por prioridade
        auth_cookies = {}
        priority_patterns = [
            # Padrões de alta prioridade (mais específicos)
            ('session', 10), ('auth', 9), ('token', 8), ('jwt', 7),
            ('login', 6), ('user', 5), ('csrf', 4), ('access', 3),
            # Padrões de média prioridade
            ('client', 2), ('id', 1)
        ]

        for cookie in cookies_list:
            if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
                name = cookie['name']
                value = cookie['value']

                # Ignora cookies claramente desnecessários
                if (name.startswith('_ga') or name.startswith('_gid') or
                    name.startswith('__utm') or name.startswith('_fbp') or
                    'analytics' in name.lower() or 'tracking' in name.lower() or
                    len(value) > 5000):  # Cookies muito grandes provavelmente não são de auth
                    continue

                # Calcula prioridade baseada nos padrões
                priority = 0
                name_lower = name.lower()
                for pattern, weight in priority_patterns:
                    if pattern in name_lower:
                        priority += weight

                # Se tem alguma prioridade ou é httpOnly (indicativo de segurança)
                if priority > 0 or cookie.get('httpOnly', False):
                    auth_cookies[name] = {
                        'value': value,
                        'priority': priority,
                        'httpOnly': cookie.get('httpOnly', False),
                        'secure': cookie.get('secure', False),
                        'domain': cookie.get('domain'),
                    }

        # Se encontrou cookies de autenticação, ordena por prioridade
        if auth_cookies:
            # Ordena por prioridade (maior primeiro), depois por httpOnly, depois por secure
            sorted_cookies = sorted(
                auth_cookies.items(),
                key=lambda x: (x[1]['priority'], x[1]['httpOnly'], x[1]['secure']),
                reverse=True
            )

            # Monta string de cookies
            cookie_parts = [f"{name}={data['value']}" for name, data in sorted_cookies]
            cookie_header = "; ".join(cookie_parts)
            referer = _domain_to_referer(sorted_cookies[0][1].get('domain'))
            print_info(f"Cookies de autenticação detectados: {len(auth_cookies)} cookies por padrões")
            return user_agent, cookie_header, referer, cookies_list

        # Estratégia 3: Fallback - extrai todos os cookies válidos
        all_cookies = {}
        fallback_domain = None
        for cookie in cookies_list:
            if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
                name = cookie['name']
                value = cookie['value']

                # Filtros básicos para evitar cookies desnecessários
                if (not name.startswith('_ga') and
                    not name.startswith('_gid') and
                    not name.startswith('__utm') and
                    len(value) < 3000 and  # Limite de tamanho
                    len(value) > 5):       # Muito pequeno provavelmente não é útil
                    all_cookies[name] = value
                    if fallback_domain is None:
                        fallback_domain = cookie.get('domain')

        if all_cookies:
            cookie_parts = [f"{name}={value}" for name, value in all_cookies.items()]
            cookie_header = "; ".join(cookie_parts)
            referer = _domain_to_referer(fallback_domain)
            print_info(f"Fallback: {len(all_cookies)} cookies extraídos (detecção universal)")
            return user_agent, cookie_header, referer, cookies_list

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print_error(f"Erro ao processar cookies: {e}")
        return None

    return None

# --- Funções de Execução ---
def _write_netscape_cookies(cookies_list, path):
    """Escreve cookies (lista do JSON exportado do navegador) em formato Netscape
    para uso com `yt-dlp --cookies`. Esse caminho preserva o escopo de domínio
    correto e elimina o aviso de 'cookies as header'."""
    lines = ["# Netscape HTTP Cookie File", "# Generated by vdl.py", ""]
    for c in cookies_list:
        if not isinstance(c, dict):
            continue
        name = c.get('name')
        value = c.get('value')
        domain = c.get('domain')
        if not (name and value and domain):
            continue
        host_only = c.get('hostOnly', False)
        # Netscape: domain field starts with '.' for cross-subdomain match
        if host_only:
            netscape_domain = domain.lstrip('.')
            include_subdomains = "FALSE"
        else:
            netscape_domain = domain if domain.startswith('.') else f".{domain}"
            include_subdomains = "TRUE"
        path_field = c.get('path', '/') or '/'
        secure = "TRUE" if c.get('secure', False) else "FALSE"
        expiration = int(c.get('expirationDate', 0)) or 0
        # Tab-separated, sem newlines em valores
        line = "\t".join([
            netscape_domain,
            include_subdomains,
            path_field,
            secure,
            str(expiration),
            name,
            value.replace('\t', ' ').replace('\n', ''),
        ])
        lines.append(line)
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")


def download_video(url, output_path, user_agent, cookie_header, referer=None, cookies_list=None):
    """Baixa o vídeo usando um diretório temporário isolado para segurança em paralelo.

    Quando cookies_list é fornecido, usa --cookies <netscape file> (preferencial,
    sem aviso de yt-dlp e com escopo de domínio correto). Caso contrário, faz
    fallback para --add-header "Cookie: ..." (caminho legado)."""
    print_info(f"Iniciando o download de: {url}")
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    ffmpeg_path = shutil.which("ffmpeg")

    with tempfile.TemporaryDirectory() as temp_dir:
        print_info(f"Usando diretório temporário isolado: {temp_dir}")

        command = [
            "yt-dlp",
            "--user-agent", user_agent,
            "--ffmpeg-location", ffmpeg_path,
            "--paths", f"temp:{temp_dir}",
            "--output", output_path,
        ]

        if cookies_list:
            cookies_path = os.path.join(temp_dir, "cookies.txt")
            _write_netscape_cookies(cookies_list, cookies_path)
            command += ["--cookies", cookies_path]
            print_info(f"Cookies em formato Netscape: {len(cookies_list)} entrada(s)")
        else:
            command += ["--add-header", f"Cookie: {cookie_header}"]

        if referer:
            print_info(f"Usando Referer: {referer}")
            command += ["--referer", referer, "--add-header", f"Origin: {referer.rstrip('/')}"]

        command.append(url)

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
            for line in iter(process.stdout.readline, ''): print_to_console_and_log(line.strip())
            process.stdout.close()
            if process.wait() != 0:
                print_error("O download falhou.")
                return False
            print_success(f"Download concluído. Vídeo salvo em: {output_path}")
            return True
        except Exception as e:
            print_error(f"Ocorreu um erro ao executar o yt-dlp: {e}")
            return False

def extract_audio(video_path, output_dir, for_transcription=True):
    """Extrai o áudio para um subdiretório 'mp3' e retorna o caminho completo.

    Quando for_transcription=True (padrão), gera mp3 mono 16kHz @ 64kbps —
    suficiente para Whisper (e ~5-8x menor que stereo q:a 0, acelerando uploads
    para a OpenAI quando há chunking). Para arquivamento, passe False.
    """
    audio_dir = os.path.join(output_dir, "mp3")
    os.makedirs(audio_dir, exist_ok=True)

    base_filename = os.path.basename(video_path)
    audio_filename = os.path.splitext(base_filename)[0] + ".mp3"
    audio_path = os.path.join(audio_dir, audio_filename)

    print_info(f"Extraindo áudio de '{video_path}' para: {audio_path}")
    if for_transcription:
        # Mono 16kHz 64kbps — alvo do Whisper, mínimo desperdício de bytes.
        command = [
            "ffmpeg", "-i", video_path, "-vn",
            "-ac", "1", "-ar", "16000", "-b:a", "64k",
            "-y", "-loglevel", "error", audio_path,
        ]
    else:
        # Qualidade alta para arquivamento (VBR ~245 kbps).
        command = ["ffmpeg", "-i", video_path, "-vn", "-q:a", "0", "-y", "-loglevel", "error", audio_path]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print_success(f"Áudio extraído com sucesso para: {audio_path}")
        return audio_path
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip() or "(nenhuma saída de erro do ffmpeg)"
        print_error(f"A extração de áudio falhou (rc={e.returncode}): {stderr}")
        return None

# --- Funções de IA ---
def load_whisper_model(model_name, use_gpu):
    """Wrapper amigável (com logs) sobre _transcription.load_whisper_model.
    Retorna (model, device) ou (None, None) em caso de falha."""
    try:
        import torch  # noqa: F401  - usado dentro do helper para checar CUDA
        from _transcription import load_whisper_model as _load
    except ImportError as e:
        print_error(f"Dependência ausente: {e}")
        return None, None
    try:
        # Pré-aviso de fallback antes de carregar
        try:
            import torch
            if use_gpu and not torch.cuda.is_available():
                print_to_console_and_log("[AVISO] CUDA não disponível. Usando CPU.", C_YELLOW)
        except Exception:
            pass
        print_info(f"Carregando modelo Whisper '{model_name}'...")
        model, device = _load(model_name, use_gpu=use_gpu)
        print_info(f"Modelo carregado (device={device}).")
        return model, device
    except Exception as e:
        print_error(f"Falha ao carregar modelo Whisper: {e}")
        return None, None


def transcribe_audio_local(audio_path, model_name, use_gpu, output_dir, model=None, device=None):
    """Transcreve áudio localmente. Aceita modelo pré-carregado para evitar
    recarregar quando processando múltiplos arquivos no modo --local diretório.
    fp16 é usado dinamicamente: True em CUDA (mais rápido), False em CPU."""
    transcription_dir = os.path.join(output_dir, "transcriptions")
    os.makedirs(transcription_dir, exist_ok=True)
    transcription_path = os.path.join(transcription_dir, os.path.basename(os.path.splitext(audio_path)[0] + ".txt"))
    print_info(f"Iniciando a transcrição LOCAL do áudio para: {transcription_path}")
    try:
        if model is None:
            model, device = load_whisper_model(model_name, use_gpu)
            if model is None:
                return None
        result = model.transcribe(audio_path, fp16=(device == "cuda"))
        with open(transcription_path, 'w', encoding='utf-8') as f: f.write(result["text"])
        print_success(f"Transcrição local salva com sucesso em: {transcription_path}")
        return result["text"]
    except Exception as e:
        print_error(f"Ocorreu um erro durante a transcrição local: {e}")
        return None

def generate_context_from_text(transcription_text, base_output_path, output_dir):
    context_dir = os.path.join(output_dir, "context")
    os.makedirs(context_dir, exist_ok=True)
    context_path = os.path.join(context_dir, os.path.basename(os.path.splitext(base_output_path)[0] + ".md"))
    print_info(f"Gerando conteúdo aprofundado com a API da OpenAI. Salvando em: {context_path}")

    try:
        prompt = _load_prompt_template("context.md").format(transcription_text=transcription_text)
    except (FileNotFoundError, KeyError) as e:
        print_error(f"Falha ao carregar prompt 'context.md': {e}")
        return

    try:
        from openai import OpenAI
        client = OpenAI()
        response = _retry_with_backoff(
            client.chat.completions.create,
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Você é um especialista em design instrucional e editor de conteúdo."},
                {"role": "user", "content": prompt}
            ],
            op_name="chat.completions (contexto)",
        )
        context_markdown = response.choices[0].message.content
        with open(context_path, 'w', encoding='utf-8') as f: f.write(context_markdown)
        print_success(f"Contexto em Markdown salvo com sucesso em: {context_path}")
    except Exception as e:
        print_error(f"Falha ao gerar contexto com a API da OpenAI: {e}")

def transcribe_and_generate_context_via_api(audio_path, base_output_path, output_dir):
    print_info("Iniciando processo unificado com a API da OpenAI...")
    try:
        from openai import OpenAI
        from pydub import AudioSegment

        client = OpenAI()

        API_LIMIT_BYTES = 24 * 1024 * 1024
        audio_size = os.path.getsize(audio_path)
        full_transcription = ""

        if audio_size > API_LIMIT_BYTES:
            print_to_console_and_log(f"[AVISO] O arquivo de áudio ({audio_size / (1024*1024):.2f} MB) excede o limite de 24 MB da API. O áudio será segmentado.", C_YELLOW)

            sound = AudioSegment.from_mp3(audio_path)
            chunk_length_ms = 10 * 60 * 1000
            chunks = [sound[i:i + chunk_length_ms] for i in range(0, len(sound), chunk_length_ms)]

            with tempfile.TemporaryDirectory(prefix="vdl_chunks_") as chunk_dir:
                print_info(f"Diretório temporário para chunks: {chunk_dir}")
                for i, chunk in enumerate(chunks):
                    chunk_path = os.path.join(chunk_dir, f"chunk_{i}.mp3")
                    chunk.export(chunk_path, format="mp3")

                    print_info(f"Enviando pedaço {i+1}/{len(chunks)} para a API de transcrição...")
                    with open(chunk_path, "rb") as audio_file:
                        transcription_response = _retry_with_backoff(
                            client.audio.transcriptions.create,
                            model="whisper-1", file=audio_file,
                            op_name=f"transcriptions chunk {i+1}/{len(chunks)}",
                        )
                    full_transcription += transcription_response.text + " "

        else:
            print_info(f"Enviando áudio '{audio_path}' para a API de transcrição...")
            with open(audio_path, "rb") as audio_file:
                transcription_response = _retry_with_backoff(
                    client.audio.transcriptions.create,
                    model="whisper-1", file=audio_file,
                    op_name="transcriptions",
                )
            full_transcription = transcription_response.text

        print_success("Áudio transcrito com sucesso pela API.")

        transcription_dir = os.path.join(output_dir, "transcriptions")
        os.makedirs(transcription_dir, exist_ok=True)
        transcription_path = os.path.join(transcription_dir, os.path.basename(os.path.splitext(audio_path)[0] + ".txt"))
        with open(transcription_path, 'w', encoding='utf-8') as f: f.write(full_transcription)
        print_info(f"Transcrição da API salva em: {transcription_path}")

        generate_context_from_text(full_transcription, base_output_path, output_dir)

    except Exception as e:
        print_error(f"Ocorreu um erro no processo unificado da API: {e}")

def main():
    """Função principal do script."""
    parser = argparse.ArgumentParser(
        prog="vdl",
        description="Baixa ou processa localmente vídeos, transcrevendo e analisando-os.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
-------------------------------------------------------------------
MODOS DE OPERAÇÃO:

1. MODO DOWNLOAD (padrão):
   Baixa um vídeo a partir de uma URL.
   Uso: vdl <URL> <nome_do_arquivo_saida> [opções]

2. MODO LOCAL (-l):
   Processa arquivo(s) de vídeo já existentes no seu computador.
   Aceita ARQUIVO ou DIRETÓRIO (busca recursiva).
   Exemplos:
     vdl -l /caminho/para/video.mp4 -c
     vdl -l . -c

-------------------------------------------------------------------
PRÉ-REQUISITOS DE AUTENTICAÇÃO:

- Para MODO DOWNLOAD:
  É necessário fornecer credenciais de uma das seguintes formas:
  1. Variável de Ambiente (Recomendado):
     export VDL_TOKEN=$(cat cookies.json | base64 -w0)
     (cookies exportados do navegador em JSON)
  2. Arquivo de cookies (cookies.json, cookie.txt, ou token.txt)
     no mesmo diretório do script ou no CWD.

  O formato legado 'User-Agent;cookie_value' (UA com ';' literal) está
  deprecado: User-Agents reais contém ';' que quebra o parser.
  Use cookies em JSON.

- Para funções de IA (-c, -u):
  A variável de ambiente OPENAI_API_KEY deve estar definida.
-------------------------------------------------------------------
"""
    )
    # Argumentos posicionais
    parser.add_argument("input", nargs='?', default=None, help="URL do vídeo (modo download) ou caminho para o arquivo local (modo local).")
    parser.add_argument("output_filename", nargs='?', default=None, help="Nome do arquivo de vídeo de saída (obrigatório no modo download).")

    # Flags de modo e configuração
    parser.add_argument("-o", "--only-download", action="store_true", help="Apenas baixa o vídeo, sem processamento adicional.")
    parser.add_argument("-l", "--local", action="store_true", help="Ativa o modo de processamento local (ignora o download).")
    parser.add_argument("-d", "--directory", default="output_dir", help="Diretório de saída principal.")
    parser.add_argument("-t", "--transcribe", action="store_true", help="Gera a transcrição LOCALMENTE.")
    parser.add_argument("-c", "--context", action="store_true", help="Gera contexto via OpenAI a partir de transcrição local.")
    parser.add_argument("-u", "--unified-mode", action="store_true", help="MODO UNIFICADO: Usa a API da OpenAI para transcrever e gerar contexto.")
    parser.add_argument("--gpu", action="store_true", help="Tenta usar a GPU para a transcrição LOCAL.")
    parser.add_argument("--whisper-model", default="base", choices=['tiny', 'base', 'small', 'medium', 'large'], help="Modelo do Whisper para transcrição LOCAL.")
    parser.add_argument("--all-contexts", action="store_true", help="Lê todos os .md em 'context' e gera um e-Book único em Markdown.")
    parser.add_argument("--referer", default=None, help="Referer HTTP para o download (necessário para CDNs com hot-link, ex.: BunnyCDN). Por padrão é inferido do domínio dos cookies.")

    args = parser.parse_args()

    # --- Validação de Argumentos ---
    # Diretório vazio quebraria os.makedirs(""); usar "." se o usuário passar -d ""
    if not args.directory or not args.directory.strip():
        args.directory = "."
    if not args.all_contexts:
        if args.local and args.output_filename is not None:
            parser.error("O argumento 'output_filename' não deve ser fornecido no modo local (-l).")
        if not args.local and args.output_filename is None:
            parser.error("O argumento 'output_filename' é obrigatório no modo de download.")

    # -c implica -t: precisa rodar antes da validação para que --gpu e
    # --whisper-model funcionem em conjunto com -c (que usa whisper local).
    if args.context:
        args.transcribe = True

    # Validações de flags conflitantes
    if args.only_download and any([args.local, args.transcribe, args.context, args.unified_mode]):
        parser.error("A flag --only-download não pode ser usada com nenhuma outra flag de processamento (-l, -t, -c, -u).")
    if args.local and args.only_download:
        parser.error("As flags --local e --only-download são mutuamente exclusivas.")
    if args.unified_mode and (args.transcribe or args.context):
        parser.error("O argumento -u (modo unificado) não pode ser usado em conjunto com -t ou -c.")
    if args.unified_mode and (args.gpu or args.whisper_model != 'base'):
        parser.error("Os argumentos --gpu e --whisper-model usam o whisper local e não podem ser combinados com -u (que envia o áudio para a API).")
    if not args.transcribe and (args.gpu or args.whisper_model != 'base'):
        parser.error("Os argumentos --gpu e --whisper-model só podem ser usados com -t ou -c.")
    if args.all_contexts and any([args.local, args.transcribe, args.context, args.unified_mode, args.only_download]):
        parser.error("A flag --all-contexts não pode ser usada em conjunto com -l, -t, -c, -u ou --only-download.")

    setup_logging()

    # Dependências
    if args.all_contexts:
        try:
            import openai  # noqa: F401
        except ImportError:
            print_error("Dependência para a API OpenAI não encontrada: 'openai'. Use: pip install openai")
            sys.exit(1)
        if not os.getenv("OPENAI_API_KEY"):
            print_error("A variável de ambiente OPENAI_API_KEY não está definida.")
            sys.exit(1)
    else:
        if not check_dependencies(args):
            sys.exit(1)

    # --- Lógica de Execução ---
    if not args.all_contexts:
        video_to_process = None
        base_output_path = None

        if args.local:
            print_info("Executando em MODO LOCAL.")
            input_path = args.input if args.input is not None else "."
            if os.path.isdir(input_path):
                from pathlib import Path
                exts = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
                try:
                    videos = [str(p) for p in Path(input_path).rglob("*") if p.is_file() and p.suffix.lower() in exts]
                except OSError as e:
                    print_error(f"Falha ao listar diretório '{input_path}': {e}")
                    sys.exit(1)
                if not videos:
                    print_error(f"Nenhum vídeo encontrado (busca recursiva) em: {os.path.abspath(input_path)}")
                    sys.exit(1)
                print_info(f"Encontrados {len(videos)} vídeo(s) (recursivo) em: {os.path.abspath(input_path)}")
                videos = sorted(videos, key=lambda s: s.lower())

                # Pré-carrega o modelo Whisper UMA VEZ se for transcrição local
                shared_model, shared_device = (None, None)
                if args.transcribe and not args.unified_mode:
                    shared_model, shared_device = load_whisper_model(args.whisper_model, args.gpu)
                    if shared_model is None:
                        sys.exit(1)

                for idx, vp in enumerate(videos, start=1):
                    print_info(f"[{idx}/{len(videos)}] Processando: {vp}")
                    base_output_path = os.path.join(args.directory, os.path.basename(vp))
                    audio_path = extract_audio(vp, args.directory)
                    if not audio_path:
                        print_error(f"Pulado por falha na extração de áudio: {vp}")
                        continue
                    if args.unified_mode:
                        transcribe_and_generate_context_via_api(audio_path, base_output_path, args.directory)
                    elif args.transcribe:
                        transcription_text = transcribe_audio_local(
                            audio_path, args.whisper_model, args.gpu, args.directory,
                            model=shared_model, device=shared_device,
                        )
                        if transcription_text and args.context:
                            generate_context_from_text(transcription_text, base_output_path, args.directory)
                video_to_process = None
                base_output_path = None
            elif os.path.isfile(input_path):
                video_to_process = input_path
                base_output_path = os.path.join(args.directory, os.path.basename(input_path))
            else:
                print_error(f"Arquivo ou diretório local não encontrado: {input_path}")
                sys.exit(1)
        else: # Modo Download
            print_info("Executando em MODO DOWNLOAD.")
            user_agent, cookie, referer, cookies_list = get_auth_details()
            if not all([user_agent, cookie]):
                sys.exit(1)

            # Override manual via CLI tem precedência sobre o auto-detectado
            effective_referer = args.referer or referer

            video_output_path = os.path.join(args.directory, args.output_filename)
            if download_video(args.input, video_output_path, user_agent, cookie, effective_referer, cookies_list):
                # --- INÍCIO DA ALTERAÇÃO ---
                # Se for apenas download, encerra o script aqui com sucesso.
                if args.only_download:
                    print_info("Modo 'only-download' ativado. Encerrando o script.")
                    sys.exit(0)
                # --- FIM DA ALTERAÇÃO ---
                video_to_process = video_output_path
                base_output_path = video_output_path
            else:
                sys.exit(1) # Sai se o download falhar

        # --- Fluxo de Processamento Pós-Download/Local ---
        if video_to_process:
            audio_path = extract_audio(video_to_process, args.directory)
            if not audio_path: sys.exit(1)

            if args.unified_mode:
                transcribe_and_generate_context_via_api(audio_path, base_output_path, args.directory)
            elif args.transcribe:
                transcription_text = transcribe_audio_local(audio_path, args.whisper_model, args.gpu, args.directory)
                if transcription_text and args.context:
                    generate_context_from_text(transcription_text, base_output_path, args.directory)

    # Consolidação opcional de todos os contextos gerados em um e-Book único
    if args.all_contexts:
        # Seleciona dinamicamente o diretório a ser lido:
        # Preferência: -d aponta direto para a pasta com .md; caso contrário, tenta -d/context;
        # Se não houver -d, usa o diretório atual; caso vazio, tenta ./context.
        cwd = os.getcwd()
        primary = args.directory if args.directory else cwd
        candidates = []
        candidates.append(primary)
        candidates.append(os.path.join(primary, "context"))
        if os.path.abspath(primary) != os.path.abspath(cwd):
            candidates.append(cwd)
            candidates.append(os.path.join(cwd, "context"))
        scan_dir = None
        for cand in candidates:
            if os.path.isdir(cand):
                md_files = [f for f in os.listdir(cand) if f.lower().endswith(".md")]
                if md_files:
                    scan_dir = cand
                    break
        if not scan_dir:
            print_error("Nenhum diretório com arquivos .md encontrado. Tente executar dentro da pasta de contextos ou usar -d <pasta>.")
            if LOG_FILE: LOG_FILE.close()
            sys.exit(1)
        def _natural_key(s):
            import re
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]
        files = sorted([f for f in os.listdir(scan_dir) if f.lower().endswith(".md")], key=_natural_key)
        print_info(f"Processando {len(files)} arquivo(s) de contexto em: {scan_dir}")
        try:
            from openai import OpenAI
            client = OpenAI()

            # MAP: lê e resume cada capítulo individualmente. Isso evita estouro
            # de context window quando há muitos arquivos .md (ou capítulos longos).
            chapter_summaries = []
            failed_files = []
            for i, fname in enumerate(files, start=1):
                path = os.path.join(scan_dir, fname)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception as e:
                    print_error(f"Falha ao ler '{fname}': {e}")
                    failed_files.append(fname)
                    continue

                print_info(f"[map {i}/{len(files)}] Resumindo capítulo: {fname}")
                map_prompt = (
                    "Você é um editor de e-books. Resuma o conteúdo abaixo em "
                    "Markdown estruturado: título sugerido, 2-3 parágrafos de "
                    "introdução do capítulo, bullets dos pontos-chave, exemplos "
                    "preservados, e principais conclusões. Mantenha termos técnicos "
                    "exatamente como estão. Capítulo " + str(i) + f" (origem: {fname}).\n\n"
                    "---\n" + content
                )
                try:
                    map_resp = _retry_with_backoff(
                        client.chat.completions.create,
                        model="gpt-4o-mini",  # mini para o map (mais barato)
                        messages=[
                            {"role": "system", "content": "Editor que produz resumos estruturados de capítulos."},
                            {"role": "user", "content": map_prompt},
                        ],
                        op_name=f"chat.completions (map cap {i})",
                    )
                    chapter_summaries.append(
                        f"# CAPÍTULO {i}: {fname}\n\n{map_resp.choices[0].message.content}"
                    )
                except Exception as e:
                    print_error(f"Falha ao resumir '{fname}': {e}")
                    failed_files.append(fname)

            if not chapter_summaries:
                print_error("Nenhum capítulo pôde ser resumido. Abortando geração do e-Book.")
                if LOG_FILE: LOG_FILE.close()
                sys.exit(1)

            combined = "\n\n".join(chapter_summaries)

            # REDUCE: consolida os resumos em um e-Book único.
            try:
                reduce_prompt = _load_prompt_template("ebook_reduce.md").format(combined=combined)
            except (FileNotFoundError, KeyError) as e:
                print_error(f"Falha ao carregar prompt 'ebook_reduce.md': {e}")
                if LOG_FILE: LOG_FILE.close()
                sys.exit(1)
            print_info(f"[reduce] Consolidando {len(chapter_summaries)} capítulo(s) em e-Book final...")
            response = _retry_with_backoff(
                client.chat.completions.create,
                model="gpt-4o",  # full model no reduce (qualidade)
                messages=[
                    {"role": "system", "content": "Você é um editor e instrutor que transforma capítulos em um e-Book coerente, completo e bem estruturado."},
                    {"role": "user", "content": reduce_prompt},
                ],
                op_name="chat.completions (reduce e-book)",
            )
            ebook_md = response.choices[0].message.content
            ebook_path = os.path.join(scan_dir, "ebook.md")
            with open(ebook_path, 'w', encoding='utf-8') as f:
                f.write(ebook_md)
            print_success(f"E-book consolidado salvo em: {ebook_path}")

            # Warning final visível se houve capítulos falhos
            if failed_files:
                print_to_console_and_log(
                    f"[AVISO] E-book gerado SEM os seguintes capítulos por falha de leitura/resumo: "
                    f"{', '.join(failed_files)} ({len(failed_files)}/{len(files)} arquivos pulados).",
                    C_YELLOW,
                )
        except Exception as e:
            print_error(f"Falha ao gerar e-Book consolidado: {e}")

    if LOG_FILE: LOG_FILE.close()

if __name__ == "__main__":
    main()
