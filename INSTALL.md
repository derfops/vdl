# Guia de Instalação do VDL

Este guia descreve como instalar todas as dependências necessárias para executar o script `vdl` em um sistema operacional Linux (como Ubuntu, Debian ou Fedora).

## Dependências Necessárias

O script `vdl` requer três componentes principais:

1.  **Python 3**: A linguagem na qual o script foi escrito.
2.  **yt-dlp**: A ferramenta de linha de comando para baixar o vídeo.
3.  **FFmpeg**: A ferramenta para processar mídia, usada aqui para extrair o áudio.

Siga os passos abaixo para instalar cada um deles.

### Passo 1: Instalar o Python 3

A maioria das distribuições Linux modernas já vem com o Python 3 instalado. Você pode verificar a instalação abrindo um terminal e digitando:

```bash
python3 --version
```

Se você receber uma resposta com a versão (ex: `Python 3.8.10`), pode pular para o próximo passo. Caso contrário, instale-o usando o gerenciador de pacotes do seu sistema.

**Para sistemas baseados em Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install python3
```

**Para sistemas baseados em Fedora/CentOS:**
```bash
sudo dnf install python3
```

### Passo 2: Instalar o yt-dlp

É altamente recomendável instalar o `yt-dlp` diretamente de seu repositório oficial para garantir que você tenha sempre a versão mais recente, o que é crucial para a compatibilidade com sites de streaming.

Execute os seguintes comandos no terminal para baixar o executável e torná-lo acessível em todo o sistema:

```bash
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
```

Em seguida, dê a ele permissão de execução:

```bash
sudo chmod a+rx /usr/local/bin/yt-dlp
```

Verifique a instalação com:
```bash
yt-dlp --version
```

### Passo 3: Instalar o FFmpeg

O FFmpeg é uma suíte de software completa para manipulação de áudio e vídeo. O `yt-dlp` o utiliza para juntar os segmentos de vídeo e áudio baixados, e nosso script o usa para extrair o áudio.

Instale-o usando o gerenciador de pacotes do seu sistema.

**Para sistemas baseados em Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Para sistemas baseados em Fedora/CentOS:**
```bash
sudo dnf install ffmpeg
```

Verifique a instalação com:
```bash
ffmpeg -version
```

## Conclusão

Após seguir estes três passos, seu sistema estará pronto para executar o script `vdl`. Para instruções sobre como usá-lo, consulte o arquivo [README.md](README.md ).
