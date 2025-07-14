#!/usr/bin/env python3
import sys
import json
import subprocess
import shutil
import os
import argparse
import platform
from datetime import datetime
import base64

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
    """Função central que imprime na tela e opcionalmente no arquivo de log."""
    plain_message = message
    for code in [C_RED, C_GREEN, C_YELLOW, C_BLUE, C_END]:
        plain_message = plain_message.replace(code, "")
    
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

# --- Funções de Setup e Verificação ---
def setup_logging():
    """Configura o logging automaticamente."""
    global LOG_FILE
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = os.path.join(log_dir, f"{timestamp}.log")
    try:
        LOG_FILE = open(log_filename, 'w', encoding='utf-8')
        print_info(f"Logging ativado. A saída será salva em: {log_filename}")
    except IOError as e:
        print_error(f"Não foi possível criar o arquivo de log: {e}")
        LOG_FILE = None

def check_dependencies(args):
    """Verifica as dependências com base nos argumentos fornecidos."""
    has_error = False
    if not args.local and not shutil.which("yt-dlp"):
        print_error("Dependência não encontrada: 'yt-dlp'. Instale-a.")
        has_error = True
    if not shutil.which("ffmpeg"):
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
    """Obtém detalhes de autenticação de VDL_TOKEN (Base64) ou cookie.txt."""
    vdl_token_b64 = os.getenv("VDL_TOKEN")
    if vdl_token_b64:
        print_info("Usando autenticação via variável de ambiente VDL_TOKEN (Base64).")
        try:
            decoded_token = base64.b64decode(vdl_token_b64).decode('utf-8')
            user_agent, cookie_value = decoded_token.split(';', 1)
            return user_agent, cookie_value
        except (base64.binascii.Error, ValueError, UnicodeDecodeError) as e:
            print_error(f"Formato inválido ou erro na decodificação de VDL_TOKEN. Use 'user_agent;cookie_value' codificado em Base64. Erro: {e}")
            return None, None
    else:
        print_info("VDL_TOKEN não encontrada. Tentando ler 'cookie.txt'.")
        try:
            with open("cookie.txt", 'r') as f: data = json.load(f)
            user_agent = data['userAgent']
            domain_key = list(data['.poseadfdc.grupoa.education'].keys())[0]
            cookie_value = data['.poseadfdc.grupoa.education'][domain_key]['aws-waf-token']['value']
            return user_agent, f"aws-waf-token={cookie_value}"
        except Exception as e:
            print_error(f"Falha ao processar o cookie.txt: {e}")
            return None, None

# --- Funções de Execução ---
def download_video(url, output_path, user_agent, cookie_header):
    print_info(f"Iniciando o download de: {url}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    ffmpeg_path = shutil.which("ffmpeg")
    command = ["yt-dlp", "--user-agent", user_agent, "--add-header", f"Cookie: {cookie_header}", "--ffmpeg-location", ffmpeg_path, "--output", output_path, url]
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

def extract_audio(video_path, output_dir):
    """Extrai o áudio para um subdiretório 'mp3' e retorna o caminho completo."""
    audio_dir = os.path.join(output_dir, "mp3")
    os.makedirs(audio_dir, exist_ok=True)
    
    base_filename = os.path.basename(video_path)
    audio_filename = os.path.splitext(base_filename)[0] + ".mp3"
    audio_path = os.path.join(audio_dir, audio_filename)

    print_info(f"Extraindo áudio de '{video_path}' para: {audio_path}")
    command = ["ffmpeg", "-i", video_path, "-vn", "-q:a", "0", "-y", "-loglevel", "error", audio_path]
    try:
        subprocess.run(command, check=True)
        print_success(f"Áudio extraído com sucesso para: {audio_path}")
        return audio_path
    except subprocess.CalledProcessError as e:
        print_error(f"A extração de áudio falhou: {e.stderr}")
        return None

# --- Funções de IA ---
def transcribe_audio_local(audio_path, model_name, use_gpu, output_dir):
    transcription_dir = os.path.join(output_dir, "transcriptions")
    os.makedirs(transcription_dir, exist_ok=True)
    transcription_path = os.path.join(transcription_dir, os.path.basename(os.path.splitext(audio_path)[0] + ".txt"))
    print_info(f"Iniciando a transcrição LOCAL do áudio para: {transcription_path}")
    try:
        import whisper, torch
        device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        if use_gpu and not torch.cuda.is_available(): print_to_console_and_log("[AVISO] CUDA não disponível. Usando CPU.", C_YELLOW)
        model = whisper.load_model(model_name, device=device)
        result = model.transcribe(audio_path, fp16=False)
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
    
    prompt = f"""
# MISSÃO

Sua missão é atuar como um especialista em design instrucional e editor de conteúdo. Você deve transformar a transcrição de uma aula em um material de estudo aprofundado e bem estruturado em formato Markdown. O resultado final deve ser tão completo que possa servir como o rascunho principal para um capítulo de e-book. O idioma de saída é **Português do Brasil**.

# CONTEXTO

A seguir está a transcrição de uma aula ou palestra. O conteúdo é denso e contém informações valiosas, incluindo conceitos técnicos, exemplos práticos e insights do instrutor. É crucial que todos os termos técnicos, nomes de ferramentas, e jargões específicos da área sejam preservados exatamente como foram ditos, sem tradução ou alteração.

# INSTRUÇÕES PASSO A PASSO (Pense como um especialista)

1.  **Análise Holística:** Leia a transcrição completa uma vez para entender o tema central, os objetivos de aprendizado implícitos e a estrutura geral da aula.
2.  **Identificação de Pilares:** Identifique os 3 a 5 pilares de conhecimento ou tópicos principais que estruturam a aula.
3.  **Extração e Expansão:** Para cada pilar, extraia os conceitos-chave, definições, exemplos e argumentos. Não se limite a copiar; reestruture as frases para maior clareza e adicione pequenas expansões contextuais onde for apropriado para transformar a linguagem falada em uma prosa escrita de alta qualidade.
4.  **Estruturação do Documento:** Organize o material extraído e expandido no formato Markdown detalhado abaixo. Seja metódico e preencha cada seção com conteúdo relevante e profundo.

# FORMATO DE SAÍDA (Markdown)

## 📖 Resumo Executivo (Executive Summary)
Um parágrafo conciso (3-5 frases) que resume o propósito da aula, os principais tópicos abordados e a principal conclusão ou habilidade ensinada.

## 🎯 Objetivos de Aprendizagem
Com base no conteúdo, liste de 3 a 5 objetivos de aprendizagem claros e mensuráveis que um aluno alcançaria ao estudar este material. Use o formato "Ao final deste capítulo, você será capaz de:".

## 🧠 Contexto Aprofundado (In-depth Context)
Explique o "porquê" por trás da aula. Onde este conhecimento se encaixa em um campo de estudo maior? Qual problema ele resolve? Por que é importante para um profissional da área? Elabore em 2-3 parágrafos.

## 📚 Detalhamento do Conteúdo (Content Breakdown)
Este é o núcleo do documento. Para cada pilar de conhecimento identificado, crie uma subseção.

### Tópico Principal 1: [Nome do Tópico]
   - **Definição/Conceito Central:** Explique o conceito principal em detalhes.
   - **Pontos-Chave (Bullet Points):** Liste os pontos mais importantes, argumentos e fatos relacionados a este tópico em formato de lista.
   - **Exemplos Práticos e Analogias:** Descreva os exemplos ou analogias usados pelo instrutor para ilustrar o conceito. Se não houver, crie um com base no conteúdo.
   - **Conexões:** Como este tópico se conecta com outros tópicos da aula ou com conhecimentos prévios?

### Tópico Principal 2: [Nome do Tópico]
   - (Repita a estrutura acima)

### (Repita para todos os tópicos principais)

## ✨ Destaques (Highlights)
Em formato de lista, cite os 3 a 5 insights mais poderosos, dicas "pro" ou momentos "eureka" da aula. São as "joias" do conteúdo.

## ⚠️ Pontos de Atenção (Lowlights / Common Pitfalls)
Em formato de lista, identifique os 2 a 3 pontos que podem ser fontes de confusão, erros comuns ou pré-requisitos que o aluno precisa dominar. O que pode dar errado se o conceito for mal aplicado?

## 🔑 Principais Lições (Key Takeaways)
Liste de 3 a 5 conclusões ou lições práticas que o aluno deve levar consigo após estudar o material. Devem ser frases acionáveis e fáceis de memorizar.

---
**TRANSCRIÇÃO BRUTA PARA ANÁLISE:**
---
{transcription_text}
"""
    try:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Você é um especialista em design instrucional e editor de conteúdo."},
                {"role": "user", "content": prompt}
            ]
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
        
        # --- INÍCIO DA LÓGICA DE SEGMENTAÇÃO ---
        # Limite da API da OpenAI (25 MB), usamos 24 MB para segurança.
        API_LIMIT_BYTES = 24 * 1024 * 1024
        
        audio_size = os.path.getsize(audio_path)
        
        full_transcription = ""

        if audio_size > API_LIMIT_BYTES:
            print_to_console_and_log(f"[AVISO] O arquivo de áudio ({audio_size / (1024*1024):.2f} MB) excede o limite de 24 MB da API. O áudio será segmentado.", C_YELLOW)
            
            sound = AudioSegment.from_mp3(audio_path)
            # 10 minutos em milissegundos
            chunk_length_ms = 10 * 60 * 1000
            chunks = [sound[i:i + chunk_length_ms] for i in range(0, len(sound), chunk_length_ms)]
            
            temp_chunk_files = []
            
            for i, chunk in enumerate(chunks):
                chunk_filename = f"temp_chunk_{i}.mp3"
                chunk.export(chunk_filename, format="mp3")
                temp_chunk_files.append(chunk_filename)
                
                print_info(f"Enviando pedaço {i+1}/{len(chunks)} para a API de transcrição...")
                with open(chunk_filename, "rb") as audio_file:
                    transcription_response = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
                full_transcription += transcription_response.text + " "
            
            # Limpeza dos arquivos temporários
            for f in temp_chunk_files:
                os.remove(f)
            print_info("Arquivos de áudio temporários foram removidos.")

        else:
            print_info(f"Enviando áudio '{audio_path}' para a API de transcrição...")
            with open(audio_path, "rb") as audio_file:
                transcription_response = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            full_transcription = transcription_response.text
        # --- FIM DA LÓGICA DE SEGMENTAÇÃO ---

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
   Uso: ./main.py <URL> <nome_do_arquivo_saida> [opções]

2. MODO LOCAL (-l):
   Processa um arquivo de vídeo que já existe no seu computador.
   Uso: ./main.py -l <caminho_para_o_video> [opções]

-------------------------------------------------------------------
PRÉ-REQUISITOS DE AUTENTICAÇÃO:

- Para MODO DOWNLOAD:
  É necessário fornecer credenciais de uma das seguintes formas:
  1. Variável de Ambiente (Recomendado):
     export VDL_TOKEN=$(echo -n 'User-Agent;cookie_value' | base64)
  2. Arquivo cookie.txt:
     Crie um arquivo 'cookie.txt' no mesmo diretório do script.

- Para funções de IA (-c, -u):
  A variável de ambiente OPENAI_API_KEY deve estar definida.
-------------------------------------------------------------------
"""
    )
    # Argumentos posicionais
    parser.add_argument("input", help="URL do vídeo (modo download) ou caminho para o arquivo local (modo local).")
    parser.add_argument("output_filename", nargs='?', default=None, help="Nome do arquivo de vídeo de saída (obrigatório no modo download).")
    
    # Flags de modo e configuração
    parser.add_argument("-l", "--local", action="store_true", help="Ativa o modo de processamento local (ignora o download).")
    parser.add_argument("-d", "--directory", default="output_dir", help="Diretório de saída principal.")
    parser.add_argument("-t", "--transcribe", action="store_true", help="Gera a transcrição LOCALMENTE.")
    parser.add_argument("-c", "--context", action="store_true", help="Gera contexto via OpenAI a partir de transcrição local.")
    parser.add_argument("-u", "--unified-mode", action="store_true", help="MODO UNIFICADO: Usa a API da OpenAI para transcrever e gerar contexto.")
    parser.add_argument("--gpu", action="store_true", help="Tenta usar a GPU para a transcrição LOCAL.")
    parser.add_argument("--whisper-model", default="base", choices=['tiny', 'base', 'small', 'medium', 'large'], help="Modelo do Whisper para transcrição LOCAL.")
    
    args = parser.parse_args()

    # --- Validação de Argumentos ---
    if args.local and args.output_filename is not None:
        parser.error("O argumento 'output_filename' não deve ser fornecido no modo local (-l).")
    if not args.local and args.output_filename is None:
        parser.error("O argumento 'output_filename' é obrigatório no modo de download.")
    if args.unified_mode and (args.transcribe or args.context):
        parser.error("O argumento -u (modo unificado) não pode ser usado em conjunto com -t ou -c.")
    if not args.transcribe and (args.gpu or args.whisper_model != 'base'):
        parser.error("Os argumentos --gpu e --whisper-model só podem ser usados com -t.")

    if args.context:
        args.transcribe = True

    setup_logging()

    if not check_dependencies(args):
        sys.exit(1)

    # --- Lógica de Execução ---
    video_to_process = None
    base_output_path = None

    if args.local:
        print_info("Executando em MODO LOCAL.")
        if not os.path.isfile(args.input):
            print_error(f"Arquivo local não encontrado: {args.input}")
            sys.exit(1)
        video_to_process = args.input
        base_output_path = os.path.join(args.directory, os.path.basename(args.input))
    else:
        print_info("Executando em MODO DOWNLOAD.")
        user_agent, cookie = get_auth_details()
        if not all([user_agent, cookie]):
            sys.exit(1)
        
        video_output_path = os.path.join(args.directory, args.output_filename)
        if download_video(args.input, video_output_path, user_agent, cookie):
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

    if LOG_FILE: LOG_FILE.close()

if __name__ == "__main__":
    main()
