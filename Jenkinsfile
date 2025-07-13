pipeline {
    // Define o agente que executará a pipeline.
    agent any

    // Define os parâmetros que aparecerão na interface do Jenkins.
    parameters {
        // Parâmetros de autenticação e download (segredos primeiro)
        password(name: 'VDL_TOKEN_PARAM', defaultValue: '', description: 'Token de autenticação no formato "User-Agent;cookie_value".')
        password(name: 'OPENAI_API_TOKEN_PARAM', defaultValue: '', description: 'Seu token da API da OpenAI (sk-...).')
        
        // Parâmetros de execução
        string(name: 'VIDEO_URL', defaultValue: '', description: 'A URL completa do vídeo M3U8 para baixar.')
        string(name: 'OUTPUT_FILENAME', defaultValue: 'video.mp4', description: 'O nome do arquivo de vídeo de saída (ex: aula_01.mp4).')
        string(name: 'OUTPUT_DIR', defaultValue: 'output_dir', description: 'Diretório de saída para os artefatos gerados.')
        
        // Parâmetros de modo de operação
        choice(name: 'EXECUTION_MODE', 
               choices: ['UNIFIED_API', 'LOCAL_TRANSCRIPTION', 'DOWNLOAD_ONLY'], 
               description: 'Escolha o modo de execução do script.')
        
        // Parâmetros opcionais para o modo de transcrição local
        choice(name: 'WHISPER_MODEL', 
               choices: ['tiny', 'base', 'small', 'medium', 'large'], 
               description: 'Modelo do Whisper para transcrição LOCAL (usado apenas se o modo for LOCAL_TRANSCRIPTION).')
        booleanParam(name: 'USE_GPU', defaultValue: false, description: 'Tentar usar GPU para transcrição LOCAL.')
    }

    stages {
        // Stage 1: Clona o código do repositório Git.
        stage('Checkout') {
            steps {
                echo 'Clonando o repositório...'
                checkout scm
            }
        }

        // Stage 2: Prepara o ambiente, instalando as dependências Python.
        stage('Setup Environment') {
            steps {
                echo 'Criando ambiente virtual e instalando dependências...'
                sh 'python3 -m venv .venv'
                sh 'source .venv/bin/activate && pip install -r requirements.txt'
                sh 'chmod +x vdl'
            }
        }

        // Stage 3: Executa o script VDL com os parâmetros fornecidos.
        stage('Execute VDL Script') {
            environment {
                // Injeta os tokens passados como parâmetros no ambiente de execução do script.
                VDL_TOKEN        = "${params.VDL_TOKEN_PARAM}"
                OPENAI_API_TOKEN = "${params.OPENAI_API_TOKEN_PARAM}"
            }
            steps {
                script {
                    echo "Iniciando o script VDL..."
                    
                    // Constrói a linha de comando dinamicamente. O log é sempre ativado.
                    def command = "./vdl '${params.VIDEO_URL}' '${params.OUTPUT_FILENAME}' -d '${params.OUTPUT_DIR}'"

                    if (params.EXECUTION_MODE == 'UNIFIED_API') {
                        command += " -u"
                    } else if (params.EXECUTION_MODE == 'LOCAL_TRANSCRIPTION') {
                        command += " -t --whisper-model ${params.WHISPER_MODEL}"
                        if (params.USE_GPU) {
                            command += " --gpu"
                        }
                    }

                    echo "Executando comando..."
                    sh "source .venv/bin/activate && ${command}"
                }
            }
        }

        // Stage 4: Arquiva os resultados para que possam ser baixados da interface do Jenkins.
        stage('Archive Artifacts') {
            steps {
                echo "Arquivando os resultados da pasta ${params.OUTPUT_DIR} e logs..."
                archiveArtifacts artifacts: "${params.OUTPUT_DIR}/**", fingerprint: true
                archiveArtifacts artifacts: 'logs/**', fingerprint: true
            }
        }
    }

    // Bloco Post-Execution: Executa ações após a conclusão da pipeline.
    post {
        always {
            echo 'Fim da execução. O workspace será mantido.'
        }
    }
}
