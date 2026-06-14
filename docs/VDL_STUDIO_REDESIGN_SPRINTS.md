# VDL Studio — Redesign 2026: Sprints de Implantação

Plano de implementação do redesign aprovado no Figma para a versão web (`studio/`).
Layout aprovado integralmente em 13/06/2026.

- **Figma:** https://www.figma.com/design/gRQmvqGEeq34lttPIuoF5w — `VDL Studio — Redesign 2026`
- **Stack atual:** frontend vanilla (`studio/frontend/` — `index.html` + `styles.css` + `app.js`, servido por nginx, **sem build tool**) + API FastAPI (`studio/api/` — `app.py` + `orchestrator.py`).
- **Princípio:** manter a stack vanilla (sem framework/build) salvo decisão explícita em contrário. Reskin progressivo, sem quebrar o que funciona.

## Node IDs das telas (para `get_design_context` / `get_screenshot` no Figma MCP)

| # | Tela | nodeId |
|---|------|--------|
| 01 | Login | `8:2` |
| 02 | Dashboard / Biblioteca | `11:2` |
| 03 | Novo lote — Download | `17:2` |
| 04 | Novo lote — Transcrição local | `17:162` |
| 05 | Fila | `20:2` |
| 06 | Jobs | `20:189` |
| 07 | Credenciais | `22:2` |
| 08 | Configurações | `22:112` |
| 09 | Trocar senha | `22:231` |
| 10 | Modal — Navegador de arquivos | `24:2` |
| 11 | Modal — Pré-visualização | `24:66` |

## Design tokens (extraídos do Figma — fonte da verdade do CSS)

```css
:root{
  /* superfícies */
  --bg:#0A0D11; --sidebar:#0C1014; --surface:#12161D; --surface-2:#171C24; --surface-3:#1E242E;
  --line:#262D38; --line-soft:#1B212A;
  /* texto */
  --text:#EAEFF5; --muted:#9AA7B6; --muted-2:#677383; --ink:#06181C;
  /* marca / status */
  --cyan:#23D1E8; --cyan-bright:#5EE6F5; --green:#34D399; --amber:#F6AF49; --red:#F35252; --violet:#8B7CF6;
  /* gradientes */
  --grad-primary:linear-gradient(180deg,#5EE6F5,#23D1E8);   /* botões primários, texto cor --ink */
  --grad-mark:linear-gradient(180deg,#23D1E8,#2B8CF2);      /* logo VDL */
  /* raios */ --r-chip:9px; --r-input:12px; --r-card:16px; --r-dialog:22px;
  /* fonte */ --font:Inter, system-ui, sans-serif;
}
```
Convenções: eyebrow = 10–11px, Semi Bold, `text-transform:uppercase`, `letter-spacing:2px`, cor `--cyan` ou `--muted-2`. Títulos de página 22px bold; títulos de card 16–17px bold; corpo 13–14px. Badges de status: pílula com ponto + texto na cor do status sobre fundo da cor a 12% + borda a 30%. Status semânticos: concluído=verde, processando/baixando=cyan, na fila=âmbar, falhou=vermelho.

## Estado do backend relevante (não reimplementar)

- **ID de lote já existe e é persistido:** `JobManager.create_*_batch` gera `batch-AAAAMMDD-HHMMSS-<hash6>` (`orchestrator.py:365` e `:419`) e salva `BatchRecord`/`JobRecord` em `jobs.json` no state dir (`VDL_STUDIO_STATE_DIR`, default `<data>/.vdl-studio-web`). `GET /api/jobs` → `list_batches()`. **O trabalho de "histórico com ID" é de UI (expor o `batch_id`, agrupar jobs por lote), não de backend.**
- **Não há autenticação:** CORS `allow_origins=["*"]`, rotas abertas. Login/sessão é trabalho novo (Sprint 1).
- Endpoints existentes: `/api/health`, `/api/runtime/{status,start,stop,ip,logs}`, `/api/files`, `/api/files/preview`, `/api/files/directory`, `/api/jobs`, `/api/jobs/download-batch`, `/api/jobs/local-transcription-batch`.

---

# Sprints

Ordem pensada para entregar valor cedo e isolar risco (auth e fundação visual primeiro).

## Sprint 0 — Fundação visual (tokens + shell)
**Objetivo:** estabelecer o sistema de design em CSS e o app-shell (sidebar + topbar) reutilizável, sem mudar comportamento.
**Escopo:** tokens em `:root`; componentes CSS base (`.btn-primary`, `.btn-secondary`, `.btn-danger`, `.card`/`.surface`, `.badge`, `.chip`, `.input`, `.segmented`, `.check`); sidebar (marca, nav com chip de ícone + item ativo, card de atividade no rodapé, bloco do usuário) e topbar (pílula de status do servidor, select de runtime, ação primária). Reskin mínimo dos painéis existentes para não quebrar.
**Fora de escopo:** auth, novas telas, lógica nova.
**Critérios de aceite:** sidebar/topbar batem visualmente com `11:2`; navegação entre painéis funciona como hoje; contraste AA; nenhuma regressão de comportamento.

## Sprint 1 — Autenticação (Login + sessão + trocar senha)
**Objetivo:** proteger o painel com login (admin/admin padrão, trocável).
**Backend:** armazenar usuário/senha (hash, ex. `pbkdf2`/`bcrypt`) em arquivo no state dir (`auth.json`), inicializando `admin`/`admin` no primeiro boot; endpoints `POST /api/auth/login` (retorna token de sessão), `POST /api/auth/change-password`, `POST /api/auth/logout`, `GET /api/auth/me`; dependency FastAPI que exige `Authorization: Bearer <token>` em todas as rotas `/api/*` exceto `health`/`login`. Token de sessão em memória + persistido o suficiente para sobreviver a reload (tabela simples no `auth.json` ou JWT com segredo).
**Frontend:** tela **01 Login** (`8:2`) como gate antes do shell; guardar token em `localStorage` e injetar header em todo `fetch`; logout no bloco do usuário; tela **09 Trocar senha** (`22:231`) com medidor de força; aviso "primeiro acesso: admin/admin". 401 → volta ao login.
**Critérios de aceite:** sem token, qualquer chamada `/api/*` (exceto health/login) responde 401 e a UI redireciona ao login; trocar senha invalida a antiga; admin/admin funciona só até a 1ª troca.

## Sprint 2 — Biblioteca / Dashboard (`11:2`) + Preview (`24:66`)
**Objetivo:** tela inicial pós-login.
**Escopo:** strip de destino (path atual + trocar/nova pasta via `/api/files`); 4 cards de métrica derivados de `/api/jobs` (ativos/aguardando/concluídos/falhas); tabela de arquivos+artefatos (de `/api/files` + status dos jobs) com busca; painel inspector com artefatos do item e ações; **modal de pré-visualização** (`24:66`) usando `/api/files/preview` (transcrição/markdown/vídeo).
**Critérios de aceite:** métricas refletem `/api/jobs`; clicar num item popula o inspector; preview abre o arquivo real.

## Sprint 3 — Novo lote (`17:2` + `17:162`) + ID de lote visível
**Objetivo:** criação de lotes com as duas operações e **histórico com ID exposto**.
**Escopo:** operation switch (Download / Transcrição por pasta); form de download (token/cookie + "validar", URLs com contagem, destino via modal, saídas: transcrição none/local/openai, extrair áudio, GPU, contexto, legendas; regras que desabilitam opções); form local (pasta entrada/saída, modelo Whisper, paralelo, GPU); wiring para `/api/jobs/download-batch` e `/api/jobs/local-transcription-batch`. **Ao criar, exibir o `batch_id` retornado** (toast/confirmação com botão "ver na fila"). Selo do modo de execução.
**Nota:** o `batch_id` já vem na resposta (`BatchRecord.to_dict()`); só exibir e levar para a Fila/Jobs.
**Critérios de aceite:** criar um lote retorna e mostra o ID; regras de habilitar/desabilitar batem com a tela; modal de pasta (`24:2`) integra no campo destino.

## Sprint 4 — Fila (`20:2`) + Jobs (`20:189`) agrupados por lote
**Objetivo:** operação e histórico.
**Escopo:** cards de runtime (Sem VPN/CyberGhost/Windscribe) com status via `/api/runtime/status`; banda de controle (Iniciar/Rebuild/Parar/Testar IP → `/api/runtime/*`); strip de IP (`/api/runtime/ip`); fila com barra de progresso por job; **Jobs**: histórico agrupado por `batch_id` (ID em destaque, jobs do lote ao expandir), filtros por status; terminal de **logs** (`/api/runtime/logs`) com colorização por serviço (gluetun/vdl).
**Critérios de aceite:** controles de runtime funcionam; a lista de jobs mostra o `batch_id` e agrupa por lote; logs carregam do runtime selecionado.

## Sprint 5 — Credenciais (`22:2`) + Configurações (`22:112`) + Modal de arquivos (`24:2`)
**Objetivo:** telas de suporte.
**Escopo:** Credenciais (card de cookie padrão; card OpenAI somente-leitura "configurada no worker"; card "Acesso ao painel" → leva à Trocar senha); Configurações (runtime padrão persistido em `localStorage`/`settings`; card Aparência opcional — tema + cor de destaque; card Sobre); **modal navegador de arquivos** (`24:2`) reutilizável com breadcrumbs e `/api/files` + `/api/files/directory`.
**Critérios de aceite:** runtime padrão persiste e pré-seleciona no Novo lote; modal de arquivos navega e devolve o path escolhido.

## Sprint 6 — Polish, estados e QA
**Objetivo:** acabamento.
**Escopo:** estados vazio/carregando/erro de cada tela; foco/teclado/aria; responsividade (sidebar colapsável já existe — manter); revisão visual lado a lado com o Figma (todas as telas); remover CSS/JS morto do layout antigo.
**Critérios de aceite:** sem painel sem estado de loading/erro; navegação por teclado no shell; paridade visual com o Figma.

---

# Prompts prontos (1 por sprint)

> Cada prompt é auto-contido para um agente de codificação (Claude Code) com acesso ao repo e ao Figma MCP. Rode na ordem. Antes de cada um, garanta a branch da sprint.

### Prompt — Sprint 0 (Fundação visual)
```
Contexto: redesign aprovado do VDL Studio (web em studio/frontend/, vanilla HTML/CSS/JS, sem build; servido por nginx). Figma file gRQmvqGEeq34lttPIuoF5w. Use o Figma MCP get_design_context/get_screenshot no nodeId 11:2 (Dashboard) como referência do shell.

Tarefa: implementar a FUNDAÇÃO VISUAL sem mudar comportamento.
1) Em studio/frontend/styles.css, defina os design tokens em :root exatamente conforme docs/VDL_STUDIO_REDESIGN_SPRINTS.md (seção "Design tokens").
2) Crie componentes CSS reutilizáveis: .btn-primary (gradiente --grad-primary, texto --ink), .btn-secondary, .btn-danger, .surface/.card, .badge (pílula com ponto), .chip (ícone), .input, .segmented, .check.
3) Reestruture o app-shell em index.html + styles.css para bater com o Figma: sidebar (marca VDL com gradiente, nav com chip de ícone por item e estado ativo em cyan, card de atividade no rodapé, bloco admin com logout) e topbar (pílula "Servidor online", select de runtime, botão primário). Mantenha a navegação entre painéis e todo o comportamento atual do app.js funcionando.

Restrições: não adicionar framework nem build tool; não alterar o backend; preservar IDs/handlers usados por app.js (ajuste seletores no app.js só se necessário). Entregue diff + uma captura/descrição de paridade com 11:2.
```

### Prompt — Sprint 1 (Autenticação)
```
Contexto: VDL Studio web (studio/frontend vanilla + studio/api FastAPI). Hoje NÃO há auth (CORS aberto, rotas livres). Telas Figma: Login 8:2, Trocar senha 22:231 (file gRQmvqGEeq34lttPIuoF5w).

Tarefa: adicionar autenticação simples (1 usuário admin) trocável.
Backend (studio/api):
- Persistir credenciais em <state_dir>/auth.json (state_dir = VDL_STUDIO_STATE_DIR, mesmo do JobManager). Inicializar admin/admin no 1º boot; senha com hash (pbkdf2_hmac ou bcrypt). Nunca logar/retornar a senha.
- Endpoints: POST /api/auth/login {user,password} -> {token}; GET /api/auth/me; POST /api/auth/change-password {current,new}; POST /api/auth/logout.
- Dependency que exige Authorization: Bearer <token> em todas as rotas /api/* exceto /api/health e /api/auth/login. Token de sessão com expiração; armazenar sessões válidas (memória + auth.json basta para este uso pessoal).
Frontend (studio/frontend):
- Tela de Login (8:2) como gate antes do shell. Guardar token em localStorage; wrapper de fetch que injeta o header e, em 401, limpa o token e volta ao Login.
- Logout no bloco do usuário da sidebar. Tela Trocar senha (22:231) com medidor de força, acessível pela tela e pelo card "Acesso ao painel" de Credenciais. Aviso "primeiro acesso: admin/admin".

Aceite: sem token, /api/jobs responde 401 e a UI vai ao Login; trocar senha invalida a anterior. Entregue diff + passos de teste manual.
```

### Prompt — Sprint 2 (Biblioteca + Preview)
```
Contexto: VDL Studio web. Figma: Dashboard/Biblioteca 11:2, modal Pré-visualização 24:66 (file gRQmvqGEeq34lttPIuoF5w). Endpoints: GET /api/jobs, GET /api/files?path=, GET /api/files/preview?path=, POST /api/files/directory.

Tarefa: implementar a tela Biblioteca conforme 11:2.
- Strip de destino: path atual + botões Trocar/Nova pasta (Nova pasta -> /api/files/directory; Trocar -> abre o modal de arquivos — se ainda não existir, stub que será feito no Sprint 5).
- 4 cards de métrica derivados de /api/jobs (ativos=running, aguardando=queued, concluídos=succeeded, falhas=failed).
- Tabela de arquivos+artefatos a partir de /api/files no destino atual, cruzando status de jobs; campo de busca filtrando por nome/status/modo; badges de status no padrão de tokens.
- Painel inspector: ao selecionar uma linha, listar artefatos (vídeo/áudio/srt/md) e ações (Pré-visualizar, Abrir jobs).
- Modal de Pré-visualização (24:66) usando /api/files/preview (render de texto p/ .srt/.md, <video> p/ mp4).

Restrições: vanilla, sem build; respeitar auth do Sprint 1 (usar o wrapper de fetch). Aceite: métricas e tabela refletem dados reais; preview abre o arquivo. Entregue diff + paridade com 11:2.
```

### Prompt — Sprint 3 (Novo lote + ID)
```
Contexto: VDL Studio web. Figma: Novo lote Download 17:2, Transcrição local 17:162, modal de pasta 24:2 (file gRQmvqGEeq34lttPIuoF5w). Endpoints: POST /api/jobs/download-batch, POST /api/jobs/local-transcription-batch. IMPORTANTE: o backend JÁ gera e persiste um batch_id (orchestrator.py:365/419) e o devolve em BatchRecord.to_dict(); NÃO reimplementar IDs.

Tarefa: implementar a tela Novo lote com as duas operações.
- Operation switch (Download por URLs / Transcrição por pasta) conforme 17:2 e 17:162.
- Form Download: token/cookie com "Validar token", textarea de URLs com contagem de válidas, destino (campo + abrir modal 24:2), saídas (transcrição none/local/openai, extrair áudio MP3, GPU, contexto .md, legendas .srt), execução sequencial/paralelo + máximo, "continuar após falha"; aplicar as REGRAS de habilitar/desabilitar (download simples desativa transcrição/contexto).
- Form local: pasta entrada/saída (modal 24:2), modo, modelo Whisper, paralelo, GPU.
- Ao submeter, chamar o endpoint e EXIBIR o batch_id retornado (toast/confirmação com "ver na Fila"). Mapear os campos da UI para os parâmetros existentes (processing_mode, concurrency, whisper_model, etc).

Restrições: vanilla; usar wrapper de fetch autenticado. Aceite: criar lote mostra o ID; regras batem com as telas. Entregue diff + teste manual de um lote.
```

### Prompt — Sprint 4 (Fila + Jobs por lote)
```
Contexto: VDL Studio web. Figma: Fila 20:2, Jobs 20:189 (file gRQmvqGEeq34lttPIuoF5w). Endpoints: /api/runtime/status|start|stop|ip|logs, GET /api/jobs (list_batches, já agrupado por batch).

Tarefa: implementar Fila e Jobs.
- Fila (20:2): cards de runtime (Sem VPN/CyberGhost/Windscribe) com status de /api/runtime/status; banda de controle Iniciar/Rebuild/Parar/Testar IP chamando /api/runtime/{start,stop,ip} com o modo selecionado; strip de resultado de IP; tabela de jobs em andamento com barra de progresso por job (running/queued).
- Jobs (20:189): histórico AGRUPADO por batch_id, com o ID em destaque e os jobs do lote ao expandir; colunas job/criado/arquivo/modo/status; filtro por status. Terminal de logs de /api/runtime/logs?mode= com colorização por serviço (gluetun=âmbar, vdl=cyan, "Initialization Sequence Completed"=verde).

Restrições: vanilla; fetch autenticado. Aceite: controles de runtime operam; jobs mostram batch_id e agrupam por lote; logs carregam. Entregue diff + teste manual.
```

### Prompt — Sprint 5 (Credenciais + Configurações + Modal de arquivos)
```
Contexto: VDL Studio web. Figma: Credenciais 22:2, Configurações 22:112, modal Navegador de arquivos 24:2 (file gRQmvqGEeq34lttPIuoF5w). Endpoints: /api/files, /api/files/directory.

Tarefa:
- Modal reutilizável "Navegador de arquivos" (24:2): breadcrumbs, lista de pastas via /api/files, "pasta acima", criar pasta via /api/files/directory, retorno do path escolhido. Integrar nos campos de destino do Sprint 2/3.
- Credenciais (22:2): card de cookie padrão (salvar localmente/no worker conforme decisão); card OpenAI somente-leitura ("configurada no worker", nunca exibir chave); card "Acesso ao painel" com botão -> Trocar senha (Sprint 1).
- Configurações (22:112): runtime padrão persistido (localStorage) e usado para pré-selecionar no Novo lote/Fila; card Aparência opcional (tema claro/escuro + cor de destaque — pode ficar como toggle visual se não houver tema claro pronto); card Sobre (versão/stack).

Restrições: vanilla; fetch autenticado. Aceite: modal navega e devolve path; runtime padrão persiste. Entregue diff.
```

### Prompt — Sprint 6 (Polish + QA)
```
Contexto: VDL Studio web, redesign implementado (Sprints 0–5). Figma file gRQmvqGEeq34lttPIuoF5w (todas as telas).

Tarefa: acabamento e QA.
- Estados vazio/carregando/erro em todas as telas (skeletons/spinners + mensagens).
- Acessibilidade: foco visível, navegação por teclado no shell e nos modais (Esc fecha, trap de foco), aria-labels.
- Responsividade: manter sidebar colapsável; garantir uso ok em telas menores.
- Paridade visual: comparar cada tela com seu nodeId (8:2, 11:2, 17:2, 17:162, 20:2, 20:189, 22:2, 22:112, 22:231, 24:2, 24:66) e corrigir desvios de espaçamento/cor/tipografia.
- Remover CSS/JS morto do layout antigo.

Aceite: nenhum painel sem loading/erro; teclado e Esc funcionam; sem código morto do layout antigo. Entregue diff + checklist de paridade por tela.
```

---

## Dependências e ordem
- Sprint 1 (auth) deve vir cedo: os Sprints 2–5 assumem o wrapper de fetch autenticado.
- Sprint 0 entrega o CSS base usado por todos.
- O modal de arquivos (24:2) é referenciado nos Sprints 2 e 3 mas só implementado de fato no 5 — usar stub até lá (ou antecipar o modal para o Sprint 2 se preferir).
- Nenhuma sprint depende de mudança no `vdl.py`/stack Docker; tudo é `studio/`.
