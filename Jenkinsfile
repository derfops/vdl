pipeline {
    // Define o agente que executará a pipeline.
    // Pode ser um nó específico com as ferramentas pré-instaladas
    // ou um contêiner Docker.
    agent any

    // Injeta as credenciais seguras como variáveis de ambiente.
    environment {
        VDL_TOKEN        = credentials('vdl-auth-token')
        OPENAI_API_TOKEN = credentials('openai-api-token')
    }

    // Define os parâmetros que aparecerão na interface do Jenkins.
    parameters {
        string(name: 'VIDEO_URL', defaultValue: '', description: 'A URL completa do vídeo M3U8 para baixar.')
        string(name: 'OUTPUT_FILENAME', defaultValue: 'video.mp4', description: 'O nome do arquivo de vídeo de saída (ex: aula_01.mp4).')
        string(name: 'OUTPUT_DIR', defaultValue: 'jenkins_output', description: 'Diretório de saída para os artefatos gerados.')
        
        choice(name: 'EXECUTION_MODE', 
               choices: ['UNIFIED_API', 'LOCAL_TRANSCRIPTION', 'DOWNLOAD_ONLY'], 
               description: 'Escolha o modo de execução do script.')
        
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
                // O Jenkins fará o checkout do repositório onde este Jenkinsfile está.
                checkout scm
            }
        }

        // Stage 2: Prepara o ambiente, instalando as dependências Python.
        stage('Setup Environment') {
            steps {
                echo 'Criando ambiente virtual e instalando dependências...'
                // Usar um ambiente virtual é uma boa prática.
                sh 'python3 -m venv .venv'
                sh 'source .venv/bin/activate && pip install -r requirements.txt'
                sh 'chmod +x vdl'
            }
        }

        // Stage 3: Executa o script VDL com os parâmetros fornecidos.
        stage('Execute VDL Script') {
            steps {
                script {
                    echo "Iniciando o script VDL..."
                    
                    // Constrói a linha de comando dinamicamente.
                    def command = "./vdl '${params.VIDEO_URL}' '${params.OUTPUT_FILENAME}' -d '${params.OUTPUT_DIR}' -l"

                    if (params.EXECUTION_MODE == 'UNIFIED_API') {
                        command += " -u"
                    } else if (params.EXECUTION_MODE == 'LOCAL_TRANSCRIPTION') {
                        command += " -t --whisper-model ${params.WHISPER_MODEL}"
                        if (params.USE_GPU) {
                            command += " --gpu"
                        }
                    }
                    // Se for 'DOWNLOAD_ONLY', nenhum argumento extra é necessário.

                    echo "Executando comando: ${command}"
                    
                    // Executa o comando dentro do ambiente virtual.
                    sh "source .venv/bin/activate && ${command}"
                }
            }
        }

        // Stage 4: Arquiva os resultados para que possam ser baixados da interface do Jenkins.
        stage('Archive Artifacts') {
            steps {
                echo "Arquivando os resultados da pasta ${params.OUTPUT_DIR} e logs..."
                // Arquiva todos os arquivos gerados (vídeo, áudio, txt, md).
                archiveArtifacts artifacts: "${params.OUTPUT_DIR}/**", fingerprint: true
                // Arquiva os logs da execução.
                archiveArtifacts artifacts: 'logs/**', fingerprint: true
            }
        }
    }

    // Bloco Post-Execution: Executa ações após a conclusão da pipeline.
    post {
        always {
            echo 'Pipeline finalizada.'
            // Limpa o workspace para a próxima execução.
            cleanWs()
        }
    }
}
