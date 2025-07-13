# Guia de Instalação

Este guia cobre a instalação do `vdl` e suas dependências.

## Passo 1: Pré-requisitos do Sistema

Você precisa ter o **Python 3.8+** e o **FFmpeg** instalados.

-   **Para Ubuntu/Debian:**
    ```bash
    sudo apt update && sudo apt install python3 python3-pip ffmpeg
    ```
-   **Para macOS (com Homebrew):**
    ```bash
    brew install python ffmpeg
    ```
-   **Para Windows (com Scoop ou Winget):**
    ```powershell
    # Usando Scoop
    scoop install python ffmpeg

    # Ou usando Winget
    winget install Python.Python.3 && winget install Gyan.FFmpeg
    ```

## Passo 2: Instalar Dependências Python

Navegue até o diretório do projeto e instale as bibliotecas necessárias usando o `requirements.txt`.

```bash
pip install -r requirements.txt
