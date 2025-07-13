# VDL - Video Downloader & Audio Extractor

`vdl` é um script de linha de comando para Linux, escrito em Python, projetado para baixar vídeos de streams HLS (M3U8) que requerem autenticação via cookies e, em seguida, extrair automaticamente o áudio do arquivo baixado.

Ele utiliza as poderosas ferramentas `yt-dlp` e `ffmpeg` para realizar as tarefas de download e processamento de mídia.

## Funcionalidades

-   **Download Autenticado**: Utiliza um arquivo `cookie.txt` para se autenticar em serviços de streaming que protegem o conteúdo via login.
-   **Extração de Áudio**: Após o download bem-sucedido do vídeo, extrai automaticamente a faixa de áudio para um arquivo `.mp3` usando `ffmpeg`.
-   **Interface Simples**: Aceita uma URL e um nome de arquivo de destino como argumentos de linha de comando.
-   **Feedback Visual**: Fornece mensagens coloridas de status (informação, sucesso, erro) para uma melhor experiência do usuário.
-   **Verificação de Dependências**: Verifica automaticamente se `yt-dlp` e `ffmpeg` estão instalados antes de executar.

## Pré-requisitos

Para usar este script, você precisa ter os seguintes programas instalados em seu sistema:

1.  **Python 3**
2.  **yt-dlp**
3.  **FFmpeg**

Para instruções detalhadas de instalação, consulte o arquivo [INSTALL.md](INSTALL.md).

## Como Usar

1.  **Instale as Dependências**: Siga as instruções no arquivo [INSTALL.md](INSTALL.md).

2.  **Prepare o Cookie**: Exporte os cookies do seu navegador para um arquivo chamado `cookie.txt` e coloque-o no mesmo diretório do script `vdl`. O formato esperado é um JSON específico, gerado por extensões como a FlagCookies.

    *Exemplo de `cookie.txt`*:
    ```json
    {"userAgent":"Mozilla/5.0...",".dominio.com":{...}}
    ```

3.  **Torne o Script Executável**: Abra o terminal e execute o seguinte comando no diretório do script:
    ```bash
    chmod +x vdl
    ```

4.  **Execute o Script**: Use o seguinte formato para iniciar o download:
    ```bash
    ./vdl "URL_DO_VIDEO" "nome_do_arquivo.mp4"
    ```

    -   `"URL_DO_VIDEO"`: O link direto para o arquivo de playlist `.m3u8`. **É crucial colocar a URL entre aspas** para evitar erros com caracteres especiais.
    -   `"nome_do_arquivo.mp4"`: O nome que você deseja dar ao arquivo de vídeo baixado.

### Exemplo de Execução

```bash
./vdl "https://servidor.de.video/stream/playlist.m3u8?token=xyz" "aula_de_calculo.mp4"
```

Após a execução, você terá dois arquivos no seu diretório:
-   `aula_de_calculo.mp4` (o vídeo completo )
-   `aula_de_calculo.mp3` (o áudio extraído)

## Solução de Problemas

-   **Erro "Comando não encontrado"**: Certifique-se de que todas as dependências em [INSTALL.md](INSTALL.md) estão corretamente instaladas e acessíveis no `PATH` do seu sistema.
-   **Erro "HTTP Error 403: Forbidden"**: Isso geralmente significa que o token na URL ou o cookie de autenticação expirou. Volte ao site, gere um novo link de vídeo e exporte um novo `cookie.txt`.
-   **Erro "Arquivo de cookie não encontrado"**: Verifique se o arquivo `cookie.txt` está no mesmo diretório que o script `vdl` e se tem o nome correto.
