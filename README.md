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

# Dê permissão de execução aos launchers
chmod +x vdl.py vdl.sh manage.sh
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
    export VDL_TOKEN="$(base64 < cookies.json | tr -d '\n')"
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
export OPENAI_API_KEY="seu_token_sk-xxxxxxxx_aqui"
```

---

## 💻 Como Usar

### Launcher Docker: `vdl.sh`

O launcher principal do projeto é o `vdl.sh`. Sem argumentos ele abre um menu
interativo para subir, derrubar, reconstruir, abrir shell, consultar logs e
testar o IP dos stacks CyberGhost e Windscribe.

```bash
./vdl.sh
./vdl.sh --help
./manage.sh --help
```

O `manage.sh` continua existindo como alias de compatibilidade, mas o caminho
recomendado é usar `./vdl.sh`.

### VDL Studio Web

O VDL Studio Web sobe como frontend separado e usa uma API local para
orquestrar os runtimes VDL. A tela inicial permite escolher:

- `Sem VPN`
- `CyberGhost`
- `Windscribe`

Suba o Studio:

```bash
./vdl.sh studio
```

Acesse:

```text
http://localhost:8787
```

O HOWTO específico das VPNs está em `docs/HOWTO-VPN.md`.

### Docker com VPN CyberGhost

O `docker-compose.yml` padrão sobe o VDL atrás do Gluetun. O serviço `vdl`
usa `network_mode: service:vpn-vdl`, então todo tráfego sai pela VPN.

Prepare o `.env`:

```bash
cp .env.example .env
```

Preencha `OPENVPN_USER` e `OPENVPN_PASSWORD`. O `vdl.sh` prepara os arquivos do
OpenVPN a partir de `glutenn_openvpn.zip` quando necessário:

```bash
./vdl.sh up
```

Verifique:

```bash
docker compose ps
docker logs gluetun --tail=80
docker exec vdl curl -s ifconfig.me
```

Alternativa Windscribe/WireGuard:

```bash
./vdl.sh up-windscribe
docker exec vdl-windscribe curl -s ifconfig.me
```

Esse modo usa `docker-compose.windscribe.yml` e o arquivo local
`Windscribe-StaticIP-WG.conf`.

### Modo Interativo: VDL Studio

Dentro do container, execute sem argumentos para abrir o menu guiado do VDL
Studio. Pelo launcher Docker, use `./vdl.sh studio` ou escolha a opção no menu:

```bash
vdl
vdl --help
```

O VDL Studio permite escolher:

- `Download em lote`
- `Retomar lote de download`
- `Gerar legendas`
- `Gerar contexto`
- `Consolidar em e-book`

No fluxo de download em lote, o terminal aceita cookie/token em Base64,
cookies JSON puros ou header `Cookie` puro, pede o diretório de destino,
aceita URLs em múltiplas linhas finalizadas por `END`, cria uma fila local em
`.vdl-studio` e nomeia os arquivos automaticamente como `01.mp4`, `02.mp4`,
etc. O lote pode rodar com 1 a 4 jobs simultâneos e pode ser retomado pelo
menu `Retomar lote de download` sem salvar credenciais em disco.

### Modo por Argumentos

O formato básico do comando é:

```bash
vdl <URL> <nome_do_arquivo.mp4> [opções]
```

### Exemplos Práticos

#### 📥 **Exemplo 1: Apenas Baixar o Vídeo e o Áudio**
O caso de uso mais simples.
```bash
vdl "https://url.do.video/playlist.m3u8?token=..." "aula_01.mp4"
```
> **Resultado**: Salva `output_dir/aula_01.mp4` e `output_dir/aula_01.mp3`.

#### 📝 **Exemplo 2: Transcrição Local com Modelo Específico**
Use a flag `-t` para transcrever localmente, escolhendo um modelo maior para mais precisão.
```bash
vdl "URL_DO_VIDEO" "aula_02.mp4" -t --whisper-model medium
```
> **Resultado**: Salva o vídeo, o áudio e a transcrição em `output_dir/transcriptions/aula_02.txt`.

#### 🧠 **Exemplo 3: Modo Unificado (A Forma Mais Fácil de Ter Tudo)**
Use a flag `-u` para que a API da OpenAI cuide de tudo: transcrição e geração de contexto.
```bash
vdl "URL_DA_REUNIAO" "reuniao_semanal.mp4" -u -d ./reunioes
```
> **Resultado**: Salva os arquivos nos subdiretórios do diretório `reunioes/`:
> - `reunioes/reuniao_semanal.mp4`
> - `reunioes/reuniao_semanal.mp3`
> - `reunioes/transcriptions/reuniao_semanal.txt`
> - `reunioes/context/reuniao_semanal.md`

#### ⚡ **Exemplo 4: Máxima Performance Local**
Combine a transcrição local (`-t`) com a geração de contexto (`-c`) e aceleração por GPU (`--gpu`).
```bash
vdl "URL_COMPLEXA" "tutorial_avancado.mp4" -c --gpu
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
