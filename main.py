#!/usr/bin/env python3
import sys
import json
import subprocess
import shutil
import os
import argparse
import platform # Importa a biblioteca para detectar o SO

# --- Cores para o terminal ---
# (O restante das cores e funções print_error, print_info, etc., continuam aqui)
# ... (código anterior inalterado) ...
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
    """Verifica as dependências e fornece instruções de instalação específicas para o SO."""
    system = platform.system()
    has_error = False

    # --- Instruções para yt-dlp ---
    if not shutil.which("yt-dlp"):
        print_error("Dependência não encontrada: 'yt-dlp'.")
        print_info("Por favor, instale-o usando o comando apropriado para o seu sistema:")
        if system == "Linux":
            print(C_YELLOW + "  Linux (Ubuntu/Debian):" + C_END)
            print("    sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp" )
            print("    sudo chmod a+rx /usr/local/bin/yt-dlp")
        elif system == "Darwin": # Darwin é o nome do kernel do macOS
            print(C_YELLOW + "  macOS (usando Homebrew):" + C_END)
            print("    brew install yt-dlp")
        elif system == "Windows":
            print(C_YELLOW + "  Windows (usando winget ou scoop):" + C_END)
            print("    winget install yt-dlp/yt-dlp")
            print(C_YELLOW + "    OU" + C_END)
            print("    scoop install yt-dlp")
        has_error = True

    # --- Instruções para ffmpeg ---
    if not shutil.which("ffmpeg"):
        print_error("Dependência não encontrada: 'ffmpeg'.")
        print_info("Por favor, instale-o usando o comando apropriado para o seu sistema:")
        if system == "Linux":
            print(C_YELLOW + "  Linux (Ubuntu/Debian):" + C_END)
            print("    sudo apt update && sudo apt install ffmpeg")
        elif system == "Darwin":
            print(C_YELLOW + "  macOS (usando Homebrew):" + C_END)
            print("    brew install ffmpeg")
        elif system == "Windows":
            print(C_YELLOW + "  Windows (usando winget ou scoop):" + C_END)
            print("    winget install Gyan.FFmpeg")
            print(C_YELLOW + "    OU" + C_END)
            print("    scoop install ffmpeg")
        has_error = True

    return not has_error

# ... (O restante do código: parse_cookie_file, download_video, extract_audio, main) ...
# ... (Cole o restante do script anterior aqui, pois ele não muda) ...
def parse_cookie_file(cookie_path="cookie.txt"):
    """Lê e analisa o arquivo de cookie JSON."""
    try:
        with open(cookie_path, 'r') as f:
            data = json.load(f)
        
        user_agent = data['userAgent']
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

def download_video(url, output_path, user_agent, cookie_header):
    """Baixa o vídeo usando yt-dlp com os cabeçalhos necessários."""
    print_info(f"Iniciando o download de: {url}")
    
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    command = [
        "yt-dlp",
        "--user-agent", user_agent,
        "--add-header", f"Cookie: {cookie_header}",
        "--output", output_path,
        "--quiet",
        "--progress",
        url
    ]
    
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print_error("O download falhou. Saída do yt-dlp:")
            print(stderr)
            return False
        
        print_success(f"Vídeo salvo em: {output_path}")
        return True
    except Exception as e:
        print_error(f"Ocorreu um erro inesperado ao executar o yt-dlp: {e}")
        return False

def extract_audio(video_path):
    """Extrai o áudio de um arquivo de vídeo usando ffmpeg."""
    audio_path = os.path.splitext(video_path)[0] + ".mp3"
    print_info(f"Extraindo áudio para: {audio_path}")
    
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-q:a", "0",
        "-y",
        "-loglevel", "error",
        audio_path
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print_success(f"Áudio extraído com sucesso para: {audio_path}")
    except subprocess.CalledProcessError as e:
        print_error("A extração de áudio falhou.")
        print(e.stderr)
def main():
    """Função principal do script."""
    # Configura o parser de argumentos
    parser = argparse.ArgumentParser(
        description="Baixa um vídeo de um stream HLS autenticado e extrai o áudio.",
        # Usamos RawTextHelpFormatter para um melhor controle da formatação do epílogo
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemplos de uso:
  # Baixar usando o diretório padrão 'output_dir'
  ./vdl "URL_DO_VIDEO" "video.mp4"

  # Baixar para um diretório específico
  ./vdl "URL_DO_VIDEO" "video.mp4" -d /caminho/para/pasta/
"""
    )
    parser.add_argument("url", help="A URL do vídeo a ser baixado.")
    parser.add_argument("filename", help="O nome do arquivo de vídeo de saída (ex: video.mp4).")
    parser.add_argument("-d", "--directory", default="output_dir", help="O diretório de saída para os arquivos. Padrão: 'output_dir'")

    # --- INÍCIO DA ALTERAÇÃO ---
    # Verifica se nenhum argumento foi passado. Se for o caso, mostra a ajuda e sai.
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    # --- FIM DA ALTERAÇÃO ---

    args = parser.parse_args()

    # A verificação de dependências deve vir depois da verificação de ajuda,
    # para que o usuário possa ver a ajuda mesmo sem as dependências instaladas.
    if not check_dependencies():
        sys.exit(1)

    # Cria o caminho completo para o arquivo de saída
    output_path = os.path.join(args.directory, args.filename)

    user_agent, cookie = parse_cookie_file()
    if not all([user_agent, cookie]):
        sys.exit(1)

    print_info("Informações de autenticação carregadas.")
    
    if download_video(args.url, output_path, user_agent, cookie):
        extract_audio(output_path)

if __name__ == "__main__":
    main()
