# 🎓 Adaptive AI Coding Tutor

> English version: [README.md](README.md)

> Персональный ментор по программированию, построенный на **LangGraph** + **RAG** + **исполнении кода в песочнице**. Студент формулирует учебную цель на естественном языке, выбирает язык (MVP: **Python** и **JavaScript**), и агент строит персональную траекторию навыков, которая **адаптируется в реальном времени**: при ошибке он направляет к целевому видеоразбору и похожим практическим заданиям; при успехе — повышает сложность и предлагает реальные кейсы. **Каждый** фрагмент кода, который показывает тьютор, — и каждое решение студента — проверяется путём **реального запуска в изолированной песочнице**, что устраняет галлюцинированный, неработающий код.

---

## 1. Что делает агент

### Краткая версия
ИИ-тьютор, который обучает программированию, **адаптируясь к ошибкам и успехам каждого студента**, и **гарантирует работоспособность всего кода**, исполняя его в песочнице перед показом.

### Подробная версия
1. **Принимает цель на естественном языке** — например, *Хочу выучить Python, чтобы автоматизировать рутинную работу*. Если цель неполная, агент задаёт уточняющие вопросы (human-in-the-loop) вместо того, чтобы догадываться.
2. **Строит персональную траекторию** атомарных навыков из Skill Graph (переменные → условия → циклы → функции → коллекции → … → мини-проект). Навыки несут общий ключ **concept**, поэтому при смене языка студентом уже освоенные концепции переиспользуются, и обучается только синтаксическая разница (delta).
3. **Адаптируется в реальном времени** — основной обучающий цикл:
   - Студент решает задачу; его код запускается на видимых **и** скрытых тестах в песочнице.
   - При **неудаче** Error Classifier диагностирует тип ошибки (off-by-one, ошибка типа, логика, таймаут, …); агент извлекает **целевой видеоразбор** для этой ошибки и предлагает **похожие практические задания**. Для продвижения дальше требуются два успеха подряд.
   - При **успехе** сложность растёт; устойчивая серия успехов выводит на **реальные кейсы** (рефакторинг, исправление багов, фичи).
4. **Гарантирует работоспособный код** — любой код, который генерирует агент, сначала запускается в песочнице; если он падает, ошибка передаётся обратно в LLM для попытки повторной генерации (reflection loop) ещё до того, как студент его увидит.

---

## 2. Описание проекта, структура и диаграммы

### 2.1 Высокоуровневая архитектура

```mermaid
graph TD
    subgraph Client
        WEB[Web app React]
        EDITOR[Monaco code editor]
    end

    subgraph Backend
        API[FastAPI gateway REST and WebSocket]
        ORCH[LangGraph orchestrator]
    end

    subgraph AI_Layer
        LLM[LLM provider OpenAI-compatible]
        EMB[Embeddings OpenAI-compatible]
    end

    subgraph RAG_Layer
        VDB[(Qdrant vector DB)]
        INGEST[Ingestion pipeline]
        CONTENT[Curated content theory videos tasks]
    end

    subgraph Execution_Layer
        LOCAL[Local code-executor container]
        RAPID[RapidAPI CodeRunner optional]
    end

    subgraph Data_Layer
        PG[(PostgreSQL profile progress checkpointer)]
        CACHE[(Redis sessions queue runtime settings cache)]
    end

    subgraph Observability
        LF[Langfuse self-hosted tracing UI on 3001]
        LFDB[(Langfuse dedicated Postgres)]
    end

    WEB --> API
    EDITOR --> API
    API --> ORCH
    ORCH --> LLM
    ORCH --> VDB
    ORCH --> LOCAL
    ORCH --> RAPID
    LLM --> EMB
    VDB --> EMB
    INGEST --> VDB
    CONTENT --> INGEST
    ORCH --> PG
    ORCH --> CACHE
    ORCH -.optional traces.-> LF
    LF --> LFDB
```

> **Runtime-настройки графа.** Адаптивные параметры (`COOLDOWN_SOLVES`, `MAX_REGEN_ATTEMPTS`, `MASTERY_SUCCESS_STREAK`, `ADVANCED_SUCCESS_STREAK`) **и переключатель on-topic guardrail `TOPIC_GUARD_ENABLED`** редактируются в рантайме через `GET/PUT /api/graph/settings` и вкладку UI **Graph Settings** — применяются **без перезапуска бэкенда**. Источник истины — Postgres; Redis (`graph:settings`) — write-through кеш.

> **On-topic guardrail.** Узел `topic_guard` выполняется первым (сразу после входа, до Intent Router) и удерживает диалог в рамках программирования и текущего процесса обучения. Используется **гибридный классификатор**: быстрая детерминированная эвристика (ключевые слова программирования + активные `language`/`current_skill`/`learning_goal` студента) и, только для неоднозначных случаев, LLM-классификатор (`chat_json`). Поведение **fail-open**: если LLM недоступен — по умолчанию считаем on-topic (с логированием), чтобы временный сбой не блокировал обучение. Отправка кода (intent=code) всегда on-topic. Запросы не по теме вежливо отклоняются (без RAG и без исполнения). Гард управляется флагом `TOPIC_GUARD_ENABLED` (по умолчанию `true`); чтобы отключить — выставьте `false` (в env как seed или через UI Graph Settings / PUT settings) в рантайме.

> **Наблюдаемость (включена из коробки).** Прогоны LangGraph (узлы + вызовы LLM) трассируются в **self-hosted Langfuse** (со своим отдельным Postgres `langfuse-db`, UI на http://localhost:3001) через Langfuse `CallbackHandler`. `docker-compose` автоматически создаёт организацию, проект и **дефолтного пользователя admin** в Langfuse и пробрасывает **те же ключи проекта** в бэкенд, поэтому трейсинг работает без ручной настройки. Это по-прежнему best-effort: если Langfuse недоступен — бэкенд работает нормально. Агрегированные метрики бэкенда (пользователи, попытки, доля успеха, средний mastery, …) доступны через `GET /api/metrics/summary` и показываются во вкладке **Graph Settings → Observability**.

### 2.2 Поток управления LangGraph

```mermaid
graph TD
    START([Student message]) --> GUARD{Topic Guard on-topic}
    GUARD -->|off-topic| RESPOND[Respond]
    GUARD -->|on-topic| ROUTER{Intent Router}

    ROUTER -->|new or changed goal| GOAL[Goal Planner with interrupt]
    ROUTER -->|theory question| RETRIEVE[RAG Retriever]
    ROUTER -->|code submission| VALIDATE[Code Validator Sandbox]
    ROUTER -->|ambiguous| CLARIFY[Clarify]

    GOAL --> SKILLPLAN[Skill Path Builder]
    SKILLPLAN --> SELECTTASK[Task Selector with uniqueness filter]

    RETRIEVE --> GENERATE[Answer Generator with guardrail]
    GENERATE --> CODECHECK{Contains code}
    CODECHECK -->|yes| SELFEXEC[Self-Execution Sandbox]
    CODECHECK -->|no| RESPOND[Respond]
    SELFEXEC -->|code works| RESPOND
    SELFEXEC -->|code broken| SELFEXEC

    VALIDATE --> DIAGNOSE{Tests result}
    DIAGNOSE -->|fail| CLASSIFY[Error Classifier]
    DIAGNOSE -->|success| PROGRESS[Progress Updater]

    CLASSIFY --> REMEDIATE[Remediation Planner video then similar tasks]
    REMEDIATE --> SELECTTASK

    PROGRESS --> ADAPT{Adaptivity Engine}
    ADAPT -->|streak| LEVELUP[Raise difficulty or real case]
    ADAPT -->|mastered| NEXTSKILL[Next skill]
    LEVELUP --> SELECTTASK
    NEXTSKILL --> SELECTTASK

    SELECTTASK --> RESPOND
    CLARIFY --> RESPOND
    RESPOND --> END([Answer to student])
```

### 2.3 Поток исполнения кода (гарантия отсутствия галлюцинаций)

```mermaid
sequenceDiagram
    participant GEN as Answer Generator
    participant SB as Sandbox Executor
    participant LLM as LLM reflection
    participant U as Student

    GEN->>SB: Generated code plus tests
    SB-->>GEN: stdout exitcode passed_tests
    alt Tests pass
        GEN-->>U: Guaranteed working code
    else Tests fail
        SB-->>LLM: Error and trace
        LLM->>SB: Corrected code retry up to N
    end
```

### 2.4 Cooldown уникальности заданий

```mermaid
graph TD
    REQ[Need a task for skill and level] --> COUNT[Current student solve count N]
    COUNT --> CAND[Candidate tasks for skill and level]
    CAND --> FILTER{For each candidate check last served solve count}
    FILTER -->|N minus last greater or equal 500 or never served| OK[Allowed]
    FILTER -->|otherwise| SKIP[Filter out]
    OK --> PICK[Pick from allowed]
    SKIP --> PICK
    PICK --> RECORD[Record serve at current solve count]
```

### 2.5 Дерево каталогов

```mermaid
graph TD
    ROOT[demo_ai_agent] --> COMPOSE[docker-compose.yml]
    ROOT --> ENV[.env.example]
    ROOT --> REQ[requirements.txt]
    ROOT --> RM[README.md]
    ROOT --> BE[backend]
    ROOT --> EXEC[code-executor]
    ROOT --> FE[frontend]

    BE --> BEAPP[app]
    BEAPP --> GR[graph state builder nodes runner]
    BEAPP --> LLMD[llm client]
    BEAPP --> RAG[rag embeddings vectorstore ingestion retriever]
    BEAPP --> EX[execution base local_docker rapidapi factory]
    BEAPP --> TK[tasks repository uniqueness]
    BEAPP --> DB[db models session skill_graph progress_repo]
    BEAPP --> SEED[seed skills content]
    BEAPP --> APIM[api routes ws]
```

```
demo_ai_agent/
├── docker-compose.yml          # Brings up the whole stack
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
├── README.md
├── backend/
│   ├── Dockerfile
│   └── app/
│       ├── main.py             # FastAPI entry (REST + WebSocket) + startup seeding
│       ├── config.py           # Settings from .env
│       ├── api/                # routes.py, ws.py
│       ├── graph/              # state.py, builder.py, runner.py, nodes/
│       ├── llm/                # client.py (OpenAI-compatible)
│       ├── rag/                # embeddings, vectorstore (Qdrant), ingestion, retriever
│       ├── execution/          # base, local_docker, rapidapi, factory (Strategy)
│       ├── tasks/              # repository.py, uniqueness.py (cooldown 500)
│       ├── db/                 # models, session, skill_graph, progress_repo
│       └── seed/               # skills.py, content/curated.py
├── code-executor/              # Isolated sandbox HTTP service (Python + Node)
│   ├── Dockerfile
│   └── runner.py
└── frontend/                   # React + Monaco editor
    ├── Dockerfile, nginx.conf, vite.config.js, package.json
    └── src/ (App.jsx, api.js, main.jsx, styles.css)
```

---

## 3. Для кого этот агент (гипотезы и предположения)

- **Новички**, которым нужен персональный темп и активное заполнение пробелов. *Гипотеза: отток на статичных курсах высок, потому что нет адаптации к индивидуальным ошибкам.*
- **Разработчики, переходящие на новый язык.** *Гипотеза: переиспользование уже освоенных концепций (циклы, функции) между языками существенно ускоряет обучение, поэтому мы обучаем только синтаксической разнице.*
- **Буткемпы и школы как white-label B2B-продукт.** *Гипотеза: B2B-покупатели готовы платить за снижение нагрузки на менторов при сохранении качества, потому что объективная проверка в песочнице масштабируется там, где ручная проверка — нет.*
- **Самоучки, обжёгшиеся на галлюцинирующих чат-ботах.** *Гипотеза: жёсткая гарантия того, что весь показанный код работает, — решающее отличие по доверию по сравнению с обычными LLM-тьюторами.*

---

## 4. Как запустить

Требования: **Docker** и **Docker Compose**.

1. Скопируйте шаблон окружения и укажите вашего LLM-провайдера:
   ```bash
   copy .env.example .env
   ```
   Задайте как минимум:
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_BASE_URL=https://api.openai.com/v1   # or your provider / local vLLM/Ollama
   LLM_MODEL=gpt-4o-mini
   EMBEDDING_MODEL=text-embedding-3-small
   EMBEDDING_DIM=1536
   ```
   Опционально включите онлайн-исполнение кода через RapidAPI, дополнительно задав `RAPIDAPI_KEY` и `RAPIDAPI_CODERUNNER_HOST` (иначе автоматически используется локальный контейнер `code-executor`).

   On-topic guardrail (задаёт начальное значение по умолчанию; также редактируется в рантайме):
   ```
   TOPIC_GUARD_ENABLED=true      # вежливо отклонять запросы не по теме; fail-open без LLM
   ```

   **Трейсинг Langfuse включён из коробки.** Оставьте ключи пустыми, чтобы
   использовать встроенные дефолты compose (`pk-lf-tutor-public-key` /
   `sk-lf-tutor-secret-key`), которыми также провижинится проект Langfuse;
   задайте свои значения, чтобы переопределить:
   ```
   LANGFUSE_PUBLIC_KEY=          # пусто → дефолт compose (pk-lf-tutor-public-key)
   LANGFUSE_SECRET_KEY=          # пусто → дефолт compose (sk-lf-tutor-secret-key)
   LANGFUSE_HOST=http://langfuse:3000   # внутренний адрес в сети compose
   # Дефолтный admin Langfuse (переопределяемо). Вход в UI: http://localhost:3001
   LANGFUSE_INIT_USER_EMAIL=admin@example.com
   LANGFUSE_INIT_USER_NAME=admin
   LANGFUSE_INIT_USER_PASSWORD=qwerty123456
   ```

2. Соберите образы и поднимите стек. Проверенный путь сборки обходит проблему DNS **EAI_AGAIN** в песочнице Docker-сборки (где `npm`/`PyPI` не могут резолвить реестры) за счёт использования BuildKit-сборщика с включённым DNS (конфигурация в [`buildkitd.toml`](buildkitd.toml:1)):

   ```bash
   copy .env.example .env

   # One-time: create a DNS-enabled BuildKit builder to work around the
   # EAI_AGAIN DNS issue in the Docker build sandbox (npm/PyPI cannot resolve)
   docker buildx create --name dnsbuilder --driver docker-container --config buildkitd.toml

   # Build images via the DNS-enabled builder
   docker buildx --builder dnsbuilder build --load -t demo_ai_agent-frontend:latest ./frontend
   docker buildx --builder dnsbuilder build --load -f backend/Dockerfile -t demo_ai_agent-backend:latest .
   docker buildx --builder dnsbuilder build --load -t demo_ai_agent-code-executor:latest ./code-executor

   # Start the whole stack
   docker compose up -d
   ```

   Это запускает: `postgres`, `qdrant`, `redis`, `code-executor`, `backend`, `frontend`, а также **`langfuse`** и его отдельный Postgres **`langfuse-db`** — все с healthcheck'ами и упорядоченными `depends_on`. При первом запуске бэкенд создаёт таблицы, заполняет Skill Graph (Python + JavaScript), создаёт строку runtime-настроек графа и индексирует подготовленный контент RAG. Образы Langfuse и его Postgres подтягиваются готовыми (pull, сборка не нужна).

3. Доступ к сервисам:
   - **Frontend:** http://localhost:3000
   - **API docs:** http://localhost:8000/docs
   - **Health:** http://localhost:8000/health
   - **Langfuse (UI трейсинга):** http://localhost:3001

### Runtime-настройки графа (без перезапуска)

Адаптивные параметры можно менять на лету:

- **UI:** откройте вкладку **Graph Settings** во фронтенде, отредактируйте значения (включая чекбокс **On-topic guard**) и нажмите Save. В этой же вкладке есть секция **Observability**: ссылка на UI трейсинга Langfuse и живая сводка метрик бэкенда.
- **API:**
  - `GET /api/graph/settings` → текущие значения (включая `TOPIC_GUARD_ENABLED`).
  - `PUT /api/graph/settings` с JSON-телом любого подмножества `COOLDOWN_SOLVES`, `MAX_REGEN_ATTEMPTS`, `MASTERY_SUCCESS_STREAK`, `ADVANCED_SUCCESS_STREAK` (положительные целые, валидируются) и/или `TOPIC_GUARD_ENABLED` (булево) → сохраняет в Postgres, обновляет Redis-кеш и возвращает новые значения. Изменения применяются сразу на следующем ходу графа — например, переключение `TOPIC_GUARD_ENABLED` включает/выключает гард в рантайме без перезапуска.

### On-topic guardrail (настраивается в рантайме)

Узел `topic_guard` ([`backend/app/graph/nodes/topic_guard.py`](backend/app/graph/nodes/topic_guard.py:1)) удерживает чат в рамках программирования и текущего процесса обучения. Он сочетает быструю эвристику по ключевым словам/контексту с LLM-классификатором для неоднозначных случаев и работает **fail-open**: при недоступности LLM по умолчанию считает запрос on-topic (с логированием), чтобы обучение не блокировалось. Запросы не по теме получают вежливый отказ (без RAG и без исполнения); отправка кода всегда on-topic. Отключить можно, выставив `TOPIC_GUARD_ENABLED=false` (env seed) либо через UI Graph Settings / `PUT /api/graph/settings` в рантайме.

### Трейсинг Langfuse (включён из коробки)

Трейсинг работает без ручной настройки: `docker-compose` автоматически создаёт организацию, проект, дефолтного пользователя **admin** и API-ключи проекта в Langfuse и пробрасывает **те же ключи** в бэкенд (`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`), поэтому `langfuse_enabled=True` с первого запуска. Прогоны графа (узлы, включая `topic_guard`, плюс вызовы LLM) появляются в UI Langfuse под проектом **tutor-project**.

- **UI Langfuse / вход admin:** http://localhost:3001 — email `admin@example.com`, пароль `qwerty123456` (имя пользователя `admin`). Переопределяется переменными `LANGFUSE_INIT_USER_*` в `.env`.
  > **Если вход admin не работает** (например, после изменения переменных `LANGFUSE_INIT_*`): эти переменные применяются Langfuse **только при первом старте с пустой базой** `langfuse-db`. На уже инициализированном томе они игнорируются. Выполните `docker compose down -v` (удалит том `langfusedbdata`) и затем `docker compose up -d` — INIT отработает на чистой БД, и пользователь admin будет создан заново.
- **Отключить трейсинг:** сделайте `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` бэкенда пустыми (и очистите дефолты в compose). Тогда бэкенд работает нормально и никогда не падает из-за Langfuse.

### Метрики бэкенда

`GET /api/metrics/summary` возвращает живые агрегаты из БД приложения: число пользователей, суммарные решения, попытки, число успехов/неудач, долю успеха, средний mastery, число выданных заданий, распределение по состояниям навыков и по типам ошибок, плюс статус/ссылку Langfuse. Они дополняют пер-трейсовые метрики latency/объёма/ошибок, которые уже даёт Langfuse. Сводка отображается во вкладке фронтенда **Graph Settings → Observability**.

4. Попробуйте сквозной сценарий: введите *I want to learn Python loops*, получите задачу, напишите решение в редакторе Monaco, нажмите **Run & Check**. Неверный ответ запускает видеоразбор + похожие задания; два верных ответа продвигают вас к следующему навыку.

> **Примечание:** На хостах, где песочница Docker-сборки нормально резолвит DNS (npm/PyPI), достаточно стандартного `docker compose up --build` (DNS-сборщик не нужен). `docker-compose.yml` фиксирует имена `image:`, которые производит шаг buildx, поэтому после сборки образы переиспользуются командой `docker compose up` без пересборки.

> **Примечание:** Адаптивная петля и sandbox-гарантия кода работают end-to-end даже без реального LLM-ключа (graceful degradation — placeholder-ключ приводит к локальному fallback эмбеддингов, и граф не падает).

> Система деградирует плавно: если эндпоинт эмбеддингов недоступен, используется детерминированный локальный fallback, а если не удаётся инициализировать checkpointer на Postgres, происходит откат на in-memory checkpointer — так что демо всё равно работает.

---

## 5. Граничные случаи и как они обрабатываются

1. **Неполные данные о цели** — студент пишет *I want to learn*. **Goal Planner** использует LangGraph `interrupt` (human-in-the-loop), чтобы спросить, какой язык и цель, вместо того чтобы догадываться. UI показывает вопрос, а ответ возобновляет граф.
2. **Ошибки внешних API** — вызовы LLM/эмбеддингов/RapidAPI обёрнуты в **retry с экспоненциальной задержкой** (`tenacity`). Если **RapidAPI** падает во время выполнения, фабрика исполнителей прозрачно **откатывается на локальный исполнитель**. Если **LLM** недоступен, агент возвращает дружелюбное сообщение, а состояние сессии сохраняется для последующего возобновления.
3. **Неоднозначный запрос** — **Intent Router** возвращает оценку уверенности; ниже порога он направляет к узлу **Clarify** и просит студента уточнить, вместо того чтобы выбирать путь наугад.
4. **Таймаут кода студента (бесконечный цикл)** — песочница применяет **жёсткий лимит по реальному времени (wall-clock)** и ограничение по памяти; результат отмечается как `timed_out`, тьютор отвечает *execution timed out — check your loop exit condition* и направляет на remediation.
5. **Конфликтующие инструкции** — студент просит *just give me the answer* во время активной задачи. **Guardrail** в Answer Generator отказывает в полном решении и возвращает **подсказки**, объясняя педагогическую причину.

---

## 6. Почему обычного детерминированного workflow недостаточно

- **Траектория не фиксирована.** Следующий шаг зависит от **типа ошибки**, истории студента и цели — это **циклический граф с ветвлением**, а не линейный pipeline.
- **Петли обратной связи незаменимы.** Повторная генерация кода до прохождения тестов (Self-Execution) и remediation до освоения — естественные **петли** в LangGraph, но неуклюжие и хрупкие в статичном workflow.
- **Маршрутизация зависит от семантики.** Классификация намерений и классификация ошибок требуют **семантического анализа LLM**, результат которого меняет маршрут — недетерминированное ветвление, которое фиксированный DAG не способен выразить.
- **Прерывания human-in-the-loop.** Пауза для уточнения цели у студента (и возобновление ровно с места остановки) требует **checkpointed, прерываемой** конечной машины состояний, чего однопроходный детерминированный pipeline предоставить не может.

---

## 7. Критерии эффективности и допустимые пороги

| Критерий | Что измеряет | Допустимый порог |
|-----------|------------------|----------------------|
| **Корректность показанного кода** | Доля показанного агентом кода, прошедшего тесты в песочнице до показа | **100% by design** (сломанный код никогда не показывается); повторная генерация успешна в **≥ 95%** случаев за **≤ 3** попытки |
| **Точность диагностики ошибок** | Доля корректно классифицированных ошибок студента | **≥ 85%** на размеченной выборке |
| **Уникальность заданий** | Доля выдач, нарушающих cooldown в 500 решений | **0%** нарушений |
| **Задержка ответа** | Медианное время ответа агента без видео | **≤ 5 s** медиана, **≤ 10 s** p95 |

Критерий уникальности напрямую проверяется через `GET /api/uniqueness/audit?user_id=...&task_id=...`.

---

## 8. Источники данных и интеграции

- **LLM API** — OpenAI-совместимый, провайдер настраивается в `.env` (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`). Используется для классификации намерений, извлечения цели, генерации ответов, классификации ошибок и повторной генерации кода.
- **Embeddings API** — OpenAI-совместимый (`EMBEDDING_MODEL`) для векторизации контента и запросов, с детерминированным офлайн-fallback.
- **Qdrant** — векторная БД, хранящая подготовленную теорию, видеоразборы и условия задач с метаданными-фильтрами (language, concept, doc_type, error_type).
- **PostgreSQL** — профиль пользователя, прогресс по навыкам, попытки, **`task_serve_history`** (cooldown уникальности) и **LangGraph checkpointer**.
- **Redis** — сессии, очередь песочницы, rate limiting и **кеш runtime-настроек графа** (`graph:settings`, источник истины — Postgres).
- **Langfuse (self-hosted, опционально)** — наблюдаемость/трейсинг LangGraph через `CallbackHandler`, с **собственным отдельным Postgres** (`langfuse-db`). UI на http://localhost:3001; включается только при заданных ключах, иначе трейсинг пропускается без влияния на бэкенд.
- **Контейнер code-executor** — изолированная локальная песочница (Python + Node) с лимитами по времени/памяти и эфемерной файловой системой.
- **RapidAPI CodeRunner** (опционально) — онлайн-исполнение кода при наличии конфигурации; фабрика откатывается на локальный при сбое.
- **Подготовленные документы** — заметки по теории, задачи по программированию (условие + видимые/скрытые тесты + проверенное в песочнице эталонное решение) и видеоразборы (с URL и тайм-кодами), заполняемые в [`backend/app/seed/content/curated.py`](backend/app/seed/content/curated.py:1).

---

## Соответствие ключевым требованиям

| # | Требование | Где |
|---|-------------|-------|
| 1 | Однокомандный `docker compose up` с healthcheck'ами + depends_on | [`docker-compose.yml`](docker-compose.yml:1) |
| 2 | `requirements.txt` со всеми Python-зависимостями | [`requirements.txt`](requirements.txt:1) |
| 3 | README со всеми разделами | этот файл |
| 4 | LLM через OpenAI-совместимый протокол, провайдер в `.env` | [`backend/app/llm/client.py`](backend/app/llm/client.py:1), [`.env.example`](.env.example:1) |
| 5 | Уникальность заданий, cooldown 500 + `task_serve_history` | [`backend/app/tasks/uniqueness.py`](backend/app/tasks/uniqueness.py:1), [`backend/app/db/models.py`](backend/app/db/models.py:1) |
| 6 | Опциональный RapidAPI CodeRunner через паттерн Strategy | [`backend/app/execution/`](backend/app/execution/base.py:1) (base/local_docker/rapidapi/factory) |
