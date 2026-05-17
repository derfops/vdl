# VDL: Video Downloader, Transcriber, and Analyzer

**VDL** é uma poderosa ferramenta de linha de comando projetada para automatizar o fluxo de trabalho de download, transcrição e análise de conteúdo de vídeo a partir de streams HLS protegidos.

Com um único comando, você pode baixar uma aula ou palestra, extrair o áudio, gerar uma transcrição precisa e, em seguida, usar a IA da OpenAI para criar um resumo contextual detalhado, pronto para servir como base para um e-book ou material de estudo.

![Fluxo de Trabalho do VDL](https://i.imgur.com/your-placeholder-image.png) <!-- Você pode criar um diagrama simples e substituir este link -->

---

## 🌟 Principais Funcionalidades

-   **Download Autenticado**: Baixa vídeos de plataformas que protegem o conteúdo com cookies, usando uma variável de ambiente (`VDL_TOKEN`) ou um arquivo `cookie.txt`.
-   **Organização Automática**: Salva os arquivos de forma estruturada em um diretório de saída, com subpastas para transcrições e resumos de contexto.
-   **Múltiplos Modos de IA**:
    -   **Transcrição Local (`-t`)**: Usa a biblioteca `openai-whisper` para transcrever o áudio diretamente na sua máquina, com suporte opcional a GPU (`--gpu`) e seleção de modelos (`--whisper-model`).
    -   **Contexto Híbrido (`-c`)**: Gera um resumo contextual detalhado via API da OpenAI a partir da transcrição gerada localmente.
    -   **Modo Unificado (`-u`)**: Simplifica todo o processo enviando o áudio diretamente para a API da OpenAI, que realiza tanto a transcrição quanto a geração do contexto, economizando recursos locais.
-   **Pronto para Automação**: Pode ser facilmente integrado a pipelines de CI/CD, como o Jenkins.
-   **Logging Detalhado**: Mantém um registro completo de cada operação para fácil depuração (`-l`).

---

## 🚀 Instalação

Para instruções detalhadas sobre como configurar o ambiente e as dependências (`Python`, `FFmpeg`), consulte o arquivo **[INSTALL.md](INSTALL.md)**.

O resumo da instalação das dependências Python é:

```bash
# Navegue até o diretório do projeto
cd /caminho/para/vdl

# Instale as bibliotecas necessárias
pip install -r requirements.txt

# Dê permissão de execução ao script
chmod +x vdl
```

---

## ⚙️ Configuração

Antes de usar, você precisa configurar a autenticação para download e, opcionalmente, a chave da API da OpenAI.

### 1. Autenticação para Download (Obrigatório)

O script oferece duas formas de autenticação, com prioridade para a variável de ambiente.

-   **(Recomendado) Variável de Ambiente `VDL_TOKEN`** com cookies em JSON:
    Exporte os cookies do navegador (extensões como "Cookie-Editor" geram JSON),
    codifique em Base64 e exporte:
    ```bash
    # Linux/macOS
    export VDL_TOKEN="$(cat cookies.json | base64 -w0)"
    ```

-   **(Alternativa) Arquivo de cookies no diretório do script ou no CWD**:
    Sem `VDL_TOKEN`, o script procura por (nesta ordem):
    `cookies.json`, `cookie.json`, `cookies.txt`, `cookie.txt`, `token.txt`.

-   **(Deprecado) Formato `User-Agent;cookie_value`**:
    O formato legado em texto simples está deprecado. User-Agents reais contêm
    `;` literais (`Mozilla/5.0 (Windows NT 10.0; Win64; x64)...`), o que quebra
    o parser. Use cookies em JSON.

#### Domínios protegidos por Referer (BunnyCDN, Cloudflare, etc.)

Streams hospedados em CDN frequentemente exigem header `Referer` apontando para
a plataforma original. O `vdl` infere automaticamente o referer a partir do
domínio dos cookies. Para override manual, use `--referer https://plataforma.com/`.

### 2. Chave da API da OpenAI (Opcional)

Para usar as funcionalidades de IA que se conectam à OpenAI (`-c` ou `-u`), defina sua chave da API.

```bash
# Exemplo para Linux/macOS
export OPENAI_API_TOKEN="seu_token_sk-xxxxxxxx_aqui"
```

---

## 💻 Como Usar

O formato básico do comando é:

```bash
./vdl <URL> <nome_do_arquivo.mp4> [opções]
```

### Exemplos Práticos

#### 📥 **Exemplo 1: Apenas Baixar o Vídeo e o Áudio**
O caso de uso mais simples.
```bash
./vdl "https://url.do.video/playlist.m3u8?token=..." "aula_01.mp4"
```
> **Resultado**: Salva `output_dir/aula_01.mp4` e `output_dir/aula_01.mp3`.

#### 📝 **Exemplo 2: Transcrição Local com Modelo Específico**
Use a flag `-t` para transcrever localmente, escolhendo um modelo maior para mais precisão.
```bash
./vdl "URL_DO_VIDEO" "aula_02.mp4" -t --whisper-model medium```
> **Resultado**: Salva o vídeo, o áudio e a transcrição em `output_dir/transcriptions/aula_02.txt`.

#### 🧠 **Exemplo 3: Modo Unificado (A Forma Mais Fácil de Ter Tudo)**
Use a flag `-u` para que a API da OpenAI cuide de tudo: transcrição e geração de contexto.
```bash
./vdl "URL_DA_REUNIAO" "reuniao_semanal.mp4" -u -d ./reunioes
```
> **Resultado**: Salva os arquivos nos subdiretórios do diretório `reunioes/`:
> - `reunioes/reuniao_semanal.mp4`
> - `reunioes/reuniao_semanal.mp3`
> - `reunioes/transcriptions/reuniao_semanal.txt`
> - `reunioes/context/reuniao_semanal.md`

#### ⚡ **Exemplo 4: Máxima Performance Local**
Combine a transcrição local (`-t`) com a geração de contexto (`-c`) e aceleração por GPU (`--gpu`).
```bash
./vdl "URL_COMPLEXA" "tutorial_avancado.mp4" -c --gpu
```
> **Resultado**: Gera todos os arquivos, mas a transcrição é processada na sua GPU, o que pode ser significativamente mais rápido.

---

## 🎛️ Referência Completa de Argumentos

| Flag              | Argumento         | Descrição                                                                                             |
| ----------------- | ----------------- | ----------------------------------------------------------------------------------------------------- |
| (posicional)      | `url`             | A URL completa do stream `.m3u8`. **Obrigatório**.                                                    |
| (posicional)      | `filename`        | O nome do arquivo de vídeo de saída (ex: `video.mp4`). **Obrigatório**.                               |
| `-d`, `--directory` | `<caminho>`       | Define o diretório de saída principal. Padrão: `output_dir`.                                          |
| `-l`, `--log`       | -                 | Ativa o salvamento de um log detalhado da operação na pasta `logs/`.                                  |
| `-t`, `--transcribe`| -                 | Ativa a transcrição de áudio **localmente** usando `openai-whisper`.                                  |
| `-c`, `--context`   | -                 | Gera um resumo de contexto via API da OpenAI a partir de uma transcrição **local**. Implica `-t`.      |
| `-u`, `--unified`   | -                 | **Modo Unificado**: Usa a API da OpenAI para transcrever e gerar contexto. **Não pode ser usado com `-t` ou `-c`**. |
| `--gpu`             | -                 | Tenta usar a GPU para a transcrição **local**. Só funciona com `-t`.                                  |
| `--whisper-model` | `[tiny,base,...]` | Escolhe o modelo do Whisper para transcrição **local**. Padrão: `base`. Funciona com `-t` ou `-c`.    |
| `--referer`       | `<URL>`           | Referer HTTP para o download. Por padrão é inferido do domínio dos cookies. |
| `--all-contexts`  | -                 | Lê todos os `.md` em `context/` e gera um e-book consolidado em Markdown via map-reduce. |
