#!/usr/bin/env python3
import sys
import json
import subprocess
import shutil
import os

# --- Cores para o terminal ---
C_RED = '\033[91m'
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_BLUE = '\033[94m'
C_END = '\033[0m'

def print_error(message):
    """Imprime uma mensagem de erro em vermelho."""
    print(f"{C_RED}[ERRO] {message}{C_END}")

def print_info(message):
    """Imprime uma mensagem informativa em azul."""
    print(f"{C_BLUE}[INFO] {message}{C_END}")

def print_success(message):
    """Imprime uma mensagem de sucesso em verde."""
    print(f"{C_GREEN}[SUCESSO] {message}{C_END}")

def check_dependencies():
    """Verifica se yt-dlp e ffmpeg estão instalados e no PATH."""
    if not shutil.which("yt-dlp"):
        print_error("O comando 'yt-dlp' não foi encontrado.")
        print_info("Por favor, instale-o seguindo as instruções em: https://github.com/yt-dlp/yt-dlp" )
        return False
    if not shutil.which("ffmpeg"):
        print_error("O comando 'ffmpeg' não foi encontrado.")
        print_info("Por favor, instale-o com 'sudo apt install ffmpeg' ou similar.")
        return False
    return True

def parse_cookie_file(cookie_path="cookie.txt"):
    """Lê e analisa o arquivo de cookie JSON."""
    try:
        with open(cookie_path, 'r') as f:
            data = json.load(f)
        
        user_agent = data['userAgent']
        # Navega pela estrutura complexa do JSON para encontrar o cookie
        domain_key = list(data['.poseadfdc.grupoa.education'].keys())[0]
        cookie_value = data['.poseadfdc.grupoa.education'][domain_key]['aws-waf-token']['value']
        
        return user_agent, f"aws-waf-token={cookie_value}"
    except FileNotFoundError:
        print_error(f"Arquivo de cookie '{cookie_path}' não encontrado.")
        return None, None
    except (KeyError, IndexError) as e:
        print_error(f"Não foi possível encontrar a chave esperada no arquivo de cookie: {e}")
        return None, None
    except json.JSONDecodeError:
        print_error(f"O arquivo '{cookie_path}' não é um JSON válido.")
        return None, None

def download_video(url, output_name, user_agent, cookie_header):
    """Baixa o vídeo usando yt-dlp com os cabeçalhos necessários."""
    print_info(f"Iniciando o download de: {url}")
    command = [
        "yt-dlp",
        "--user-agent", user_agent,
        "--add-header", f"Cookie: {cookie_header}",
        "--output", output_name,
        "--quiet", # Suprime a saída normal do yt-dlp
        "--progress", # Mostra uma barra de progresso limpa
        url
    ]
    
    try:
        # Usamos Popen para ter mais controle e poderíamos ler a saída se quiséssemos
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print_error("O download falhou. Saída do yt-dlp:")
            print(stderr)
            return False
        
        print_success(f"Vídeo salvo como: {output_name}")
        return True
    except Exception as e:
        print_error(f"Ocorreu um erro inesperado ao executar o yt-dlp: {e}")
        return False

def extract_audio(video_path):
    """Extrai o áudio de um arquivo de vídeo usando ffmpeg."""
    # Define o nome do arquivo de áudio (mesmo nome, extensão .mp3)
    audio_path = os.path.splitext(video_path)[0] + ".mp3"
    print_info(f"Extraindo áudio para: {audio_path}")
    
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",          # Remove o vídeo
        "-q:a", "0",    # Melhor qualidade de áudio (VBR)
        "-y",           # Sobrescreve o arquivo de saída se ele existir
        audio_path
    ]

    try:
        # Usamos -loglevel error para mostrar apenas erros críticos do ffmpeg
        result = subprocess.run(command, check=True, capture_output=True, text=True, extra_opts=['-loglevel', 'error'])
        print_success(f"Áudio extraído com sucesso para: {audio_path}")
    except subprocess.CalledProcessError as e:
        print_error("A extração de áudio falhou.")
        print(e.stderr)

def main():
    """Função principal do script."""
    if not check_dependencies():
        sys.exit(1)

    if len(sys.argv) != 3:
        print_error("Uso incorreto.")
        print_info(f"Exemplo: ./{os.path.basename(__file__)} <URL> <nome-destino.mp4>")
        sys.exit(1)

    video_url = sys.argv[1]
    output_filename = sys.argv[2]

    user_agent, cookie = parse_cookie_file()
    if not all([user_agent, cookie]):
        sys.exit(1)

    print_info("Informações de autenticação carregadas.")
    
    if download_video(video_url, output_filename, user_agent, cookie):
        extract_audio(output_filename)

if __name__ == "__main__":
    main()
