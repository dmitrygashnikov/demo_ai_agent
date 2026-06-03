# 🎓 Adaptive AI Coding Tutor

> English version: [README.md](README.md)

> Персональный ментор по программированию, построенный на **LangGraph** + **RAG** + **исполнении кода в песочнице**. Студент формулирует учебную цель на естественном языке, выбирает язык (MVP: **Python** и **JavaScript**), выбирает **человекочитаемую секцию/тематику** из сворачиваемого сайдбара (или добавляет свою), и агент строит персональную траекторию навыков, которая **адаптируется в реальном времени**: при ошибке он направляет к целевому видеоразбору, **≥4 проверенным на доступность ссылкам из веб-поиска + краткому объяснению** и похожим практическим заданиям; при успехе подтверждает решение (не переформулируя только что решённую задачу) и явно **предлагает следующую задачу**, повышая сложность и предлагая реальные кейсы. Задачи могут **выдаваться из подготовленного контента или генерироваться на лету LLM с привязкой к веб-поиску** — и **каждый** фрагмент кода, который показывает тьютор, эталонное решение каждой сгенерированной задачи и каждое решение студента проверяются путём **реального запуска в изолированной песочнице**, что устраняет галлюцинированный, неработающий код. Сгенерированные/найденные ссылки **сохраняются в link store**, который проверяет доступность во время выдачи, заменяет «мёртвые» ссылки и удаляет хронически нерабочие.

---

## 1. Что делает агент

### Краткая версия
ИИ-тьютор, который обучает программированию, **адаптируясь к ошибкам и успехам каждого студента**, и **гарантирует работоспособность всего кода**, исполняя его в песочнице перед показом.

### Подробная версия
1. **Принимает цель на естественном языке** — например, *Хочу выучить Python, чтобы автоматизировать рутинную работу*. Если цель неполная, агент задаёт уточняющие вопросы (human-in-the-loop) вместо того, чтобы догадываться.
2. **Строит персональную траекторию** атомарных навыков из Skill Graph (переменные → условия → циклы → функции → коллекции → … → мини-проект). Навыки несут общий ключ **concept**, поэтому при смене языка студентом уже освоенные концепции переиспользуются, и обучается только синтаксическая разница (delta). **У каждого засеянного навыка в обоих языках (Python и JavaScript) есть хотя бы одно проверенное в песочнице практическое задание**, а выбор навыка теперь **учитывает контент** — агент выбирает самый ранний неосвоенный навык, у которого реально есть задания, поэтому новый студент всегда получает настоящую задачу, а не тупик. **Задачи различаются не только формулировкой, но и по сути** — введена таксономия `exercise_type` (`implement_return`, `predict_output`, `trace_value`, `find_the_bug`, `fill_in_the_blank`, `refactor`, `conditions_branching`, `loops_accumulate`, `io_transform`), и селектор **ротирует тип**, смещаясь прочь от типа, выданного в прошлый раз, чтобы подряд не шли однотипные упражнения. Для answer-типов (`predict_output`/`trace_value`) студент **вводит ожидаемое значение/вывод**, а не пишет функцию — ответ проверяется через `check_typed_answer` детерминированным сравнением.
3. **Адаптируется в реальном времени** — основной обучающий цикл:
   - Студент решает задачу; его код запускается на видимых **и** скрытых тестах в песочнице.
   - При **неудаче** разбор **привязан к реально присланному коду/вводу студента и реальной ошибке из песочницы** (а не к обобщённой теории): per-test диагностика `ERROR:`/`FAIL:` и top-level traceback извлекаются из вывода харнесса; есть **детект «это вообще не код»** — пустая отправка, `SyntaxError` (с указанием строки/столбца и неправильных символов) или текст-проза вместо кода. Error Classifier диагностирует тип ошибки (off-by-one, ошибка типа, логика, таймаут, …) на основе **реального сигнала**; узел `web_search` строит code-grounded объяснение и подбирает **целевые ссылки по конкретному символу ошибки** (например, `TypeError`). **Каждое объяснение ошибки гарантированно содержит ≥4 проверенных на доступность ссылки** (берутся из сохранённого link store, дополняются живым поиском, с офлайн-засеянным «полом»). Итоговое **одно сообщение** соблюдает порядок: **(а) упрощённый трейс → (б) блок `Explanation` со встроенными ссылками + пример правильного решения (из `reference_solution`) → (в) похожая задача** (проваленная не переформулируется). Для продвижения дальше требуются два успеха подряд.
   - На **теоретические/программистские вопросы** агент возвращает запрошенную информацию **плюс follow-up практическое упражнение**, чтобы обучение оставалось практическим, а не заканчивалось простым ответом.
   - При **успехе** агент подтверждает прохождение **без переформулирования только что решённой задачи** и явно **предлагает следующую задачу** (`➡️ Следующая задача`); сложность растёт, устойчивая серия успехов выводит на **реальные кейсы** (рефакторинг, исправление багов, фичи), а при исчерпании траектории показывается аккуратное сообщение о завершении.
4. **Берёт задачи из подготовленного контента или из живого интернета** — помимо подготовленных задач, тьютор может **сгенерировать свежую задачу на лету с помощью LLM**, привязав её к **веб-поиску**, с **автоматически сгенерированными тестами, проверенными в песочнице** (цикл reflection/regeneration с переиспользованием `code-executor`), прежде чем задача будет выдана. Сгенерированные задачи подчиняются тому же cooldown уникальности в 500 решений + `task_serve_history` и адресуются по `task_id` (id вида `gen_<uuid>`). Весь путь **fail-open**: если поиск/LLM недоступны, происходит откат на подготовленный контент, и ход никогда не падает. Управляется флагом `INTERNET_TASKS_ENABLED` (по умолчанию `true`).
5. **Переключает секцию/тематику из сайдбара** — левый сайдбар показывает **человекочитаемые секции** (тематики) вместо сырых строк `skill_id`: **по 20 засеянных секций на язык** (Python и JavaScript) плюс создаваемые пользователем, с выпадающим списком языка, живым фильтром, кликабельными карточками и текущей секцией, закреплённой и подсвеченной сверху. Выбор секции задаёт свободную тематику пользователя (`topic`, ортогональную языку/навыку; она **не** портит прогресс в skill-графе) **и запускает свежий тематический ход**, который отменяет ранее выданную задачу и генерирует новую тематическую задачу — поэтому один и тот же навык (например, циклы) можно практиковать в выбранной студентом области (анализ данных, веб-скрейпинг, геймдев, финансы, …). У каждой секции есть **пиктограмма «?»**, которая отправляет в чат ≥4 проверенные вводные статьи + ≥1 видео по концепции секции. Пустая тематика = ровно то нейтральное поведение, что и сегодня.
6. **Гарантирует работоспособный код** — любой код, который генерирует агент, и эталонное решение каждой сгенерированной задачи сначала запускаются в песочнице; если падают, ошибка передаётся обратно в LLM для попытки повторной генерации (reflection loop) ещё до того, как студент это увидит.

---

## 2. Описание проекта, структура и диаграммы

### 2.1 Высокоуровневая архитектура

```mermaid
graph TD
    subgraph Client
        WEB[Web app React collapsible sidebar plus draggable splitter]
        EDITOR[Monaco code editor]
        SECTIONUI[Sidebar sections panel language dropdown filter add section]
    end

    subgraph Backend
        API[FastAPI gateway REST and WebSocket]
        AUTH[Auth layer JWT bcrypt get_current_user]
        ORCH[LangGraph orchestrator]
        GEN[Task Generator LLM plus sandbox verify]
        SEARCHCLIENT[Web search client MCP first SearXNG fallback]
    end

    subgraph AI_Layer
        LLM[LLM provider OpenAI-compatible]
        EMB[Embeddings OpenAI-compatible]
    end

    subgraph Search_Layer
        MCP[SearXNG MCP server container]
        SEARX[SearXNG container]
    end

    subgraph RAG_Layer
        VDB[(Qdrant vector DB)]
        INGEST[Ingestion pipeline]
        CONTENT[Curated content theory videos tasks plus seeded intro links]
        LINKSTORE[Link store availability check plus pruning]
    end

    subgraph Execution_Layer
        LOCAL[Local code-executor container]
        RAPID[RapidAPI CodeRunner optional]
    end

    subgraph Data_Layer
        PG[(PostgreSQL profile progress sections remediation_links generated tasks checkpointer)]
        CACHE[(Redis sessions queue runtime settings cache)]
    end

    subgraph Observability
        LF[Langfuse self-hosted tracing UI on 3001]
        LFDB[(Langfuse dedicated Postgres)]
    end

    WEB --> API
    EDITOR --> API
    SECTIONUI --> API
    API --> AUTH
    AUTH --> ORCH
    API --> ORCH
    ORCH --> LLM
    ORCH --> VDB
    ORCH --> LOCAL
    ORCH --> RAPID
    ORCH --> GEN
    ORCH --> SEARCHCLIENT
    GEN --> LLM
    GEN --> LOCAL
    SEARCHCLIENT --> MCP
    MCP --> SEARX
    SEARCHCLIENT -.fallback direct HTTP.-> SEARX
    LLM --> EMB
    VDB --> EMB
    INGEST --> VDB
    CONTENT --> INGEST
    ORCH --> LINKSTORE
    SEARCHCLIENT --> LINKSTORE
    LINKSTORE --> PG
    ORCH --> PG
    ORCH --> CACHE
    ORCH -.optional traces.-> LF
    LF --> LFDB
```

> **Веб-поиск + интернет-задачи (fail-open).** Узел `web_search` и Task Generator расширяют AI-слой. Поисковый клиент бэкенда ([`backend/app/search/`](backend/app/search/__init__.py:1)) сначала пробует **SearXNG MCP server** (инструмент `web_search` поверх Streamable HTTP на `http://searxng-mcp:8077/mcp`), затем откатывается на **прямой SearXNG JSON**, затем на пустой результат — **никогда не выбрасывая исключение**. Task Generator ([`backend/app/tasks/generator.py`](backend/app/tasks/generator.py:1)) генерирует LLM-задачи, эталонное решение которых **проверяется в песочнице** до выдачи. Каждая новая зависимость деградирует плавно: сбой поиска → remediation без ссылок/из подготовленного контента; сбой генерации → подготовленная задача; MCP недоступен → прямой SearXNG HTTP; SearXNG недоступен → пропускаем ссылки, оставляем объяснение от LLM. Управляется флагом `INTERNET_TASKS_ENABLED` и свойством конфигурации `search_enabled`.

> **Link store (сохранение + доступность + удаление + гарантия ≥4 ссылок).** Прагматичный реляционный **link store** ([`backend/app/rag/link_store.py`](backend/app/rag/link_store.py:1)) сохраняет сгенерированные/найденные ссылки remediation и intro в таблицу `remediation_links`, чтобы они **переиспользовались между студентами**. Во время выдачи ссылки, которые вот-вот будут показаны, **проверяются на доступность** (конкурентный HTTP `HEAD`, таймаут ≤4с, **fail-open**); «мёртвые» ссылки отбрасываются и **заменяются через веб-поиск** (реальный `web_search` инъектируется при старте через `set_replacement_search(...)` в [`backend/app/main.py`](backend/app/main.py:1)), а вновь найденные ссылки сохраняются обратно. Ссылка, которая **не открывается более 50 раз в скользящем 3-дневном окне** (`FAIL_THRESHOLD=50`, `FAIL_WINDOW=3 days`, `record_failure`), **удаляется** из стора. **Каждое объяснение ошибки гарантированно содержит ≥4 проверенные ссылки** (`get_verified_links(..., min_links=4)`), с офлайн-**засеянным «полом»** (≥4 статьи + ≥1 видео на концепцию/язык в [`backend/app/seed/content/curated_links.py`](backend/app/seed/content/curated_links.py:1)), поэтому гарантия выполняется даже без egress.

> **Runtime-настройки графа.** Адаптивные параметры (`COOLDOWN_SOLVES`, `MAX_REGEN_ATTEMPTS`, `MASTERY_SUCCESS_STREAK`, `ADVANCED_SUCCESS_STREAK`) **и переключатель on-topic guardrail `TOPIC_GUARD_ENABLED`** редактируются в рантайме через `GET/PUT /api/graph/settings` и вкладку UI **Graph Settings** — применяются **без перезапуска бэкенда**. Источник истины — Postgres; Redis (`graph:settings`) — write-through кеш.

> **On-topic guardrail.** Узел `topic_guard` выполняется первым (сразу после входа, до Intent Router) и удерживает диалог в рамках программирования и текущего процесса обучения. Используется **гибридный классификатор**: быстрая детерминированная эвристика (ключевые слова программирования + активные `language`/`current_skill`/`learning_goal` студента) и, только для неоднозначных случаев, LLM-классификатор (`chat_json`). Поведение **fail-open**: если LLM недоступен — по умолчанию считаем on-topic (с логированием), чтобы временный сбой не блокировал обучение. Отправка кода (intent=code) всегда on-topic. Запросы не по теме вежливо отклоняются (без RAG и без исполнения). Гард управляется флагом `TOPIC_GUARD_ENABLED` (по умолчанию `true`); чтобы отключить — выставьте `false` (в env как seed или через UI Graph Settings / PUT settings) в рантайме.

> **Наблюдаемость (включена из коробки).** Прогоны LangGraph (узлы + вызовы LLM) трассируются в **self-hosted Langfuse** (со своим отдельным Postgres `langfuse-db`, UI на http://localhost:3001) через Langfuse `CallbackHandler`. `docker-compose` автоматически создаёт организацию, проект и **дефолтного пользователя admin** в Langfuse и пробрасывает **те же ключи проекта** в бэкенд, поэтому трейсинг работает без ручной настройки. Проверка релизов/обновлений Langfuse отключена (`LANGFUSE_UI_RELEASE_CHECK_ENABLED=false`), чтобы шумные, но некритичные ошибки `checkUpdate` не появлялись в офлайн-окружениях или средах с заблокированным egress. Это по-прежнему best-effort: если Langfuse недоступен — бэкенд работает нормально. Агрегированные метрики бэкенда (пользователи, попытки, доля успеха, средний mastery, …) доступны через `GET /api/metrics/summary` и показываются во вкладке **Graph Settings → Observability**.

### 2.2 Поток управления LangGraph

```mermaid
graph TD
    START([Student message]) --> GUARD{Topic Guard on-topic}
    GUARD -->|off-topic| RESPOND[Respond]
    GUARD -->|on-topic| ROUTER{Intent Router}

    ROUTER -->|new or changed goal| GOAL[Goal Planner with interrupt]
    ROUTER -->|theory question| RETRIEVE[RAG Retriever]
    ROUTER -->|code submission| VALIDATE[Code Validator Sandbox]
    ROUTER -->|section change| SECTION[Section change discard old task new theme]
    ROUTER -->|ambiguous| CLARIFY[Clarify]

    GOAL --> SKILLPLAN[Skill Path Builder]
    SECTION --> SKILLPLAN
    SKILLPLAN --> SELECTTASK[Task Selector curated or generated plus uniqueness filter]

    RETRIEVE --> GENERATE[Answer Generator with guardrail]
    GENERATE --> CODECHECK{Contains code}
    CODECHECK -->|yes| SELFEXEC[Self-Execution Sandbox]
    CODECHECK -->|no| RESPOND[Respond]
    SELFEXEC -->|code works| RESPOND
    SELFEXEC -->|code broken| SELFEXEC

    VALIDATE --> DIAGNOSE{Tests result}
    DIAGNOSE -->|fail| CLASSIFY[Error Classifier]
    DIAGNOSE -->|success| PROGRESS[Progress Updater]

    CLASSIFY --> WEBSEARCH[Web Search link store plus at least 4 verified links]
    WEBSEARCH --> REMEDIATE[Remediation Planner links excerpt then similar task]
    REMEDIATE --> SELECTTASK

    PROGRESS --> ADAPT{Adaptivity Engine}
    ADAPT -->|streak| LEVELUP[Raise difficulty or real case]
    ADAPT -->|mastered| NEXTSKILL[Next skill]
    ADAPT -->|track complete| DONE[Graceful completion message]
    LEVELUP --> OFFERNEXT[Offer next task]
    NEXTSKILL --> OFFERNEXT
    OFFERNEXT --> SELECTTASK

    SELECTTASK --> RESPOND
    CLARIFY --> RESPOND
    DONE --> RESPOND
    RESPOND --> END([Answer to student])
```

> **Выбор навыка с учётом контента.** Skill Path Builder ([`backend/app/graph/nodes/skill_path.py`](backend/app/graph/nodes/skill_path.py:1)) выбирает самый ранний неосвоенный навык, у которого реально есть задания (с аккуратным fallback), поэтому новый студент никогда не попадает на навык без контента. Task Selector ([`backend/app/graph/nodes/task_selector.py`](backend/app/graph/nodes/task_selector.py:1)) проходит по траектории skill-графа до следующего навыка, у которого есть задания, прежде чем сдаться, и выдаёт более понятное, действенное сообщение вместо прежнего тупика `No tasks available for this skill yet.`

> **Code-grounded путь неудачи + порядок блоков.** При проваленной отправке `code_validator` ([`backend/app/graph/nodes/code_validator.py`](backend/app/graph/nodes/code_validator.py:1)) извлекает **реальный** сигнал ошибки (`extract_student_error`: `ERROR:`/`FAIL:` из stdout + stderr-traceback) и прогоняет **детект не-кода** (`detect_input_issue`: пусто / `SyntaxError` со строкой-столбцом / проза вместо кода; для answer-типов детект пропускается, т.к. вводится значение). Узел `web_search` ([`backend/app/graph/nodes/web_search.py`](backend/app/graph/nodes/web_search.py:1)) выполняется **между** `error_classifier` и Remediation Planner (`error_classifier → web_search → remediation`); запрос обогащается **конкретным символом ошибки** (например, `TypeError`), а `Explanation` строится **по реальному коду студента + реальной ошибке** (LLM, с детерминированным code-grounded fallback). Ссылки берутся через **link store** с помощью `get_verified_links(..., min_links=4)`, поэтому **каждое объяснение содержит ≥4 проверенные на доступность ссылки** (переиспользование сохранённых + живой дозапрос + засеянный «пол»). Remediation Planner ([`backend/app/graph/nodes/remediation.py`](backend/app/graph/nodes/remediation.py:1)) собирает **одно сообщение в строгом порядке: (а) упрощённый трейс → (б) `Explanation` со встроенными ссылками + пример правильного решения (из `reference_solution`)**; Task Selector ([`backend/app/graph/nodes/task_selector.py`](backend/app/graph/nodes/task_selector.py:1)) затем **дописывает (в) `🔁 похожую задачу`** через `remediation_prefix`, **не затирая разбор**. Полностью **fail-open**: пустой поиск → ссылки берутся из засеянного «пола», code-grounded объяснение сохраняется; если похожей задачи нет — разбор всё равно не теряется.

> **Путь смены секции (новая тематическая задача, старая отменяется).** Выбор секции в сайдбаре вызывает `run_turn` с `section_change=True`/`section_title` ([`backend/app/graph/runner.py`](backend/app/graph/runner.py:1)); новые каналы состояния `section_change`, `section_title` и `cancelled_task_id` живут в [`backend/app/graph/state.py`](backend/app/graph/state.py:1). Intent Router ([`backend/app/graph/nodes/router.py`](backend/app/graph/nodes/router.py:1)) направляет ход на `intent="section"` → Skill Path Builder → Task Selector. Task Selector ([`backend/app/graph/nodes/task_selector.py`](backend/app/graph/nodes/task_selector.py:1)) **отбрасывает ранее выданную задачу** (записанную как `cancelled_task_id`, её больше не выдают) и генерирует **свежую тематическую задачу**, добавляя в начало строку `🎨 Theme set to "…"` — это исправляет прежний баг, когда смена тематики печатала сообщение, но не порождала новую задачу.

> **Путь сгенерированной задачи + предложение следующей.** Когда задана `topic`, фильтр cooldown не оставляет ничего свежего или включён `INTERNET_TASKS_ENABLED`, Task Selector вызывает Task Generator ([`backend/app/tasks/generator.py`](backend/app/tasks/generator.py:1)), чтобы сгенерировать проверенную в песочнице задачу (`task_source="generated"`, id `gen_<uuid>`), исключая только что решённый id. При успехе Adaptivity Engine ([`backend/app/graph/nodes/adaptivity.py`](backend/app/graph/nodes/adaptivity.py:1)) выставляет `offer_next_task=True`, и селектор добавляет явный префикс **➡️ Следующая задача**; при исчерпании траектории вместо этого возвращается аккуратное сообщение о завершении.

> **Теоретические ответы включают практику.** Answer Generator ([`backend/app/graph/nodes/answer_generator.py`](backend/app/graph/nodes/answer_generator.py:1)) добавляет после теоретического ответа follow-up практическое упражнение с учётом навыка, поэтому теоретический/программистский вопрос возвращает информацию **плюс** конкретное упражнение, которое можно попробовать следующим.

> **Вариативность задач по типу (`exercise_type`).** У `Task` ([`backend/app/tasks/repository.py`](backend/app/tasks/repository.py:1)) и `GeneratedTask` ([`backend/app/db/models.py`](backend/app/db/models.py:1)) есть поле `exercise_type` (миграция «на месте» при старте в [`backend/app/main.py`](backend/app/main.py:1)). Подготовленный контент ([`backend/app/seed/content/curated.py`](backend/app/seed/content/curated.py:1)) диверсифицирован — ранние навыки (`py_variables`, `py_io`, `py_loops`, `js_variables`, …) несут ≥3 разных типа. Типы: `implement_return`, `predict_output`, `trace_value`, `find_the_bug`, `fill_in_the_blank`, `refactor`, `conditions_branching`, `loops_accumulate`, `io_transform`. **Answer-типы** (`predict_output`/`trace_value`) не требуют функции — студент вводит ожидаемое значение/вывод, проверка через `check_typed_answer()` ([`backend/app/execution/base.py`](backend/app/execution/base.py:1)) толерантным сравнением; code-производящие типы используют обычный харнесс. Task Selector **ротирует тип** через `last_exercise_type` в state (смещение прочь от прошлого типа; это предпочтение, а не жёсткое ограничение — никогда не упирается в тупик), а генератор параметризуется целевым типом. Рендер промпта условный по типу (answer-типы просят значение, `fill_in_the_blank` показывает шаблон с `___`, `find_the_bug`/`refactor` показывают исходный код). Фронтенд ([`frontend/src/App.jsx`](frontend/src/App.jsx:1)) узнаёт тип через `last_exercise_type` в state и для answer-типов меняет подпись/кнопку на «ввести ответ» — тот же текстовый ввод уходит как submission, бэкенд интерпретирует его корректно.

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

> **Самоописывающиеся отправки.** Отправка кода несёт собственный `task_id`: `CodeRequest` ([`backend/app/api/routes.py`](backend/app/api/routes.py:1)) принимает опциональный `task_id` (плюс опциональные `skill`/`language`), `run_turn` ([`backend/app/graph/runner.py`](backend/app/graph/runner.py:1)) прокидывает его в состояние как `current_task_id`, а фронтенд `submitCode` ([`frontend/src/api.js`](frontend/src/api.js:1)) / [`frontend/src/App.jsx`](frontend/src/App.jsx:1) отправляют текущий `task_id` при каждом **Run & Check**. Поэтому отправка проверяется против правильной задачи даже при отсутствии состояния чекпойнта. Id сгенерированных задач (`gen_<uuid>`) резолвятся через динамический стор ([`backend/app/tasks/dynamic_store.py`](backend/app/tasks/dynamic_store.py:1)), поэтому **Run & Check** против интернет-задачи проверяется ровно так же, как против подготовленной.

> **Сгенерированные задачи тоже проверяются в песочнице.** Task Generator ([`backend/app/tasks/generator.py`](backend/app/tasks/generator.py:1)) переиспользует ровно этот reflection-цикл: сгенерированная задача выдаётся только после того, как её автоматически сгенерированное **эталонное решение проходит все видимые + скрытые тесты** в `code-executor`; если нет — ошибка передаётся обратно в LLM (с ограничением `MAX_REGEN_ATTEMPTS`) для повторной генерации, а если проверка всё равно не проходит, система откатывается на подготовленный контент. Таким образом, гарантия отсутствия галлюцинаций распространяется и на интернет-задачи.

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

> **Полное покрытие заданиями.** Подготовленный контент теперь включает задание `practice` для **каждого** засеянного навыка в **обоих** языках — `py_variables, py_io, py_conditions, py_loops, py_functions, py_collections, py_dicts, py_strings, py_errors, py_oop, py_comprehensions, py_recursion, py_modules, py_api, py_project` и JavaScript-эквиваленты (`js_*`) — все они определены в [`backend/app/seed/content/curated.py`](backend/app/seed/content/curated.py:1), и каждое эталонное решение проверено в песочнице (34/34 задания проходят свои видимые + скрытые тесты). В сочетании с выбором навыка с учётом контента у фильтра уникальности всегда есть реальный кандидат.

> **Сгенерированные задачи используют тот же cooldown.** Интернет-задачи (`gen_<uuid>`) проходят через **ту же** машинерию `task_serve_history` + фильтр уникальности + `record_serve` без изменений (она работает с любым `.id`). Поскольку сгенерированные задачи обычно уникальны для каждого запроса, они естественно проходят cooldown в 500 решений, а выдачи всё равно записываются для аудита — поэтому критерий эффективности «0% нарушений cooldown» выполняется и для подготовленных, и для сгенерированных задач.

### 2.5 Дерево каталогов

```mermaid
graph TD
    ROOT[demo_ai_agent] --> COMPOSE[docker-compose.yml]
    ROOT --> ENV[.env.example]
    ROOT --> REQ[requirements.txt]
    ROOT --> RM[README.md]
    ROOT --> BE[backend]
    ROOT --> EXEC[code-executor]
    ROOT --> SX[searxng settings.yml]
    ROOT --> SXMCP[searxng-mcp Dockerfile server.py]
    ROOT --> FE[frontend]

    BE --> BEAPP[app]
    BEAPP --> GR[graph state builder nodes runner incl web_search node]
    BEAPP --> LLMD[llm client]
    BEAPP --> RAG[rag embeddings vectorstore ingestion retriever link_store]
    BEAPP --> SEARCH[search mcp_client searxng_client]
    BEAPP --> EX[execution base local_docker rapidapi factory]
    BEAPP --> TK[tasks repository uniqueness generator dynamic_store]
    BEAPP --> DB[db models incl Section RemediationLink session skill_graph progress_repo]
    BEAPP --> SEED[seed skills sections content incl curated_links]
    BEAPP --> APIM[api routes sections ws]
```

```
demo_ai_agent/
├── docker-compose.yml          # Brings up the whole stack
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies (incl. mcp==1.12.4)
├── README.md
├── searxng/                    # SearXNG meta-search config (JSON output enabled)
│   └── settings.yml
├── searxng-mcp/                # In-repo SearXNG MCP server (web_search tool, Streamable HTTP)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py
├── backend/
│   ├── Dockerfile
│   └── app/
│       ├── main.py             # FastAPI entry (REST + WebSocket) + startup seeding/migration
│       ├── config.py           # Settings from .env (incl. SEARXNG_*, INTERNET_TASKS_ENABLED)
│       ├── api/                # routes.py, sections.py (sections/links/intro), ws.py
│       ├── graph/              # state.py, builder.py, runner.py, nodes/ (incl. web_search.py)
│       ├── llm/                # client.py (OpenAI-compatible)
│       ├── rag/                # embeddings, vectorstore (Qdrant), ingestion, retriever, link_store.py (availability + pruning)
│       ├── search/             # __init__.py (fail-open orchestrator), mcp_client.py, searxng_client.py
│       ├── execution/          # base, local_docker, rapidapi, factory (Strategy)
│       ├── tasks/              # repository.py, uniqueness.py (cooldown 500), generator.py, dynamic_store.py
│       ├── db/                 # models (incl. GeneratedTask, Section, RemediationLink + users.topic/current_section_id), session, skill_graph, progress_repo
│       └── seed/               # skills.py, sections.py (20 sections/lang), content/curated.py, content/curated_links.py (intro/remediation floor)
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
   EMBEDDING_DIM=2560 
   ```
   Опционально включите онлайн-исполнение кода через RapidAPI, дополнительно задав `RAPIDAPI_KEY` и `RAPIDAPI_CODERUNNER_HOST` (иначе автоматически используется локальный контейнер `code-executor`).

   On-topic guardrail (задаёт начальное значение по умолчанию; также редактируется в рантайме):
   ```
   TOPIC_GUARD_ENABLED=true      # вежливо отклонять запросы не по теме; fail-open без LLM
   ```

   **Веб-поиск + интернет-задачи (опционально, fail-open).** Они обеспечивают ссылки/выдержку для remediation на пути неудачи и живую LLM-генерацию задач. Дефолты работают из коробки в сети compose; тьютор остаётся работоспособным, даже если эти сервисы недоступны:
   ```
   SEARXNG_URL=http://searxng:8080            # внутренний URL сервиса SearXNG
   SEARXNG_MCP_URL=http://searxng-mcp:8077    # внутренний URL сервера SearXNG MCP
   SEARXNG_MCP_PORT=8077                       # порт, на котором слушает MCP-сервер
   SEARXNG_SECRET=changeme-searxng-secret      # server.secret_key для SearXNG
   INTERNET_TASKS_ENABLED=true                 # мастер-переключатель LLM-генерации задач (false = только подготовленные)
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

   **Аутентификация приложения (JWT)** — у приложения-репетитора СВОЙ вход, отдельный от учётки admin в Langfuse. Дефолты работают «из коробки»; переопределяются в `.env`:
   ```
   JWT_SECRET=dev-insecure-change-me-in-production   # СМЕНИТЕ в продакшене
   JWT_EXPIRE_MINUTES=10080                           # время жизни токена (7 дней)
   # Дефолтный пользователь приложения, создаётся при старте бэкенда (вход в приложение):
   APP_DEFAULT_USER_EMAIL=admin@example.com
   APP_DEFAULT_USER_PASSWORD=qwerty123456
   APP_DEFAULT_USER_NAME=admin
   APP_DEFAULT_USER_LANGUAGE=python
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
   docker buildx --builder dnsbuilder build --load -t demo_ai_agent-searxng-mcp:latest ./searxng-mcp

   # Start the whole stack
   docker compose up -d
   ```

   Это запускает: `postgres`, `qdrant`, `redis`, `code-executor`, **`searxng`** и встроенный в репозиторий сервер **`searxng-mcp`**, `backend`, `frontend`, а также **`langfuse`** и его отдельный Postgres **`langfuse-db`** — все с healthcheck'ами и упорядоченными `depends_on`. При первом запуске бэкенд создаёт таблицы (включая новые таблицы `sections` и `remediation_links`), выполняет идемпотентные миграции `ALTER TABLE … ADD COLUMN IF NOT EXISTS` для `users.topic` и `users.current_section_id` (для обновлений «на месте»), заполняет Skill Graph (Python + JavaScript), засевает **по 20 человекочитаемых секций на язык** + вводные/remediation **«пол» ссылок** в link store, создаёт строку runtime-настроек графа и индексирует подготовленный контент RAG. Образы Langfuse и его Postgres подтягиваются готовыми, образ **`searxng`** (**`searxng/searxng:2026.5.31-7159b8aed`**) также подтягивается — собирается только `searxng-mcp` (вместе с backend/frontend/code-executor). Бэкенд `depends_on` `searxng`/`searxng-mcp` с `condition: service_started` (не блокирующее), поэтому стек поднимается, даже когда поиск недоступен (fail-open); `searxng-mcp` зависит от `searxng: service_healthy`.

   > **Тег образа SearXNG.** Образ зафиксирован на **датированном теге** (`searxng/searxng:2026.5.31-7159b8aed`), а не `:latest`, для воспроизводимых офлайн-сборок. Изначально запланированный тег `2024.12.10-cc59cf0` больше не опубликован на Docker Hub (manifest unknown) и был перепиннен на ближайший доступный недавний стабильный датированный релиз, проверенный на шаге пересборки/верификации — это тег, который сейчас в [`docker-compose.yml`](docker-compose.yml:70).

3. Доступ к сервисам:
   - **Frontend:** http://localhost:3000 — сначала открывается **экран авторизации** (вход / регистрация). Войдите дефолтным пользователем `admin@example.com` / `qwerty123456`, после чего появится учебный интерфейс.
   - **API docs:** http://localhost:8000/docs
   - **Health:** http://localhost:8000/health
   - **Health поиска:** http://localhost:8000/api/search/health → `{"mcp":bool,"searxng":bool}` (диагностика; best-effort). На проверенной пересборке возвращает `{"mcp":true,"searxng":true}`.
   - **Langfuse (UI трейсинга):** http://localhost:3001
   - **SearXNG JSON API (debug, опционально):** по умолчанию только внутренний; раскомментируйте маппинг порта `8080:8080` в [`docker-compose.yml`](docker-compose.yml:79), чтобы напрямую запрашивать `http://localhost:8080/search?q=python+loops&format=json`.

### Аутентификация (вход в приложение)

У приложения-репетитора **собственная** JWT-аутентификация, полностью **отдельная от учётной записи admin в Langfuse** (у той свой вход, её мы не трогаем).

- **Открытая регистрация, без верификации почты.** Любой может создать аккаунт через `POST /api/auth/register` (email, пароль, опц. имя и язык). Пароли хешируются **bcrypt** (passlib); возвращается подписанный **JWT**.
- **Эндпоинты:**
  - `POST /api/auth/register` → создаёт пользователя, **сразу инициализирует учебный профиль**, возвращает JWT + пользователя. `409`, если email занят.
  - `POST /api/auth/login` → email + пароль → JWT + пользователь. `401` при неверных кредах.
  - `GET /api/auth/me` → текущий пользователь (нужен `Authorization: Bearer <token>`). `401` без токена или с битым токеном.
- **Защищённые эндпоинты.** `/api/goal`, `/api/chat`, `/api/submit_code`, `/api/resume`, `/api/progress/*` и WebSocket `/ws` требуют валидный токен. `user_id` всегда берётся из токена (поле `user_id` в теле запроса игнорируется), так что клиент не может действовать от чужого имени. WebSocket принимает токен через query-параметр `?token=` либо первое сообщение `{type:"auth",token}`.
- **Дефолтный пользователь приложения.** При старте бэкенд засевает дефолтного пользователя из `APP_DEFAULT_USER_*` (по умолчанию `admin@example.com` / `qwerty123456`, имя `admin`, язык `python`) с инициализированным профилем. Это и готовый вход, и страховка, гарантирующая наличие валидной строки `users`. Переопределяется в `.env`. Форма входа подставляет email-плейсхолдер и показывает демо-креды как подсказку (пароль **не** захардкожен в JS).
- **Инициализация профиля устраняет FK-ошибку skill_progress.** Регистрация/логин (и начало каждого хода графа) вызывают `ensure_user_profile(user_id, language)`, который get-or-create создаёт строку `users` и сеет первые записи skill_progress. В сочетании с get-or-create-семантикой в репозитории прогресса это значит, что чат/код работают **сразу после входа**, ещё до `/api/goal` — прежняя FK-ошибка `skill_progress` больше не возникает.
- **Поток на фронтенде.** Перед основным UI показывается экран **Вход / Регистрация**. При успехе JWT сохраняется в `localStorage` и прикрепляется как `Authorization: Bearer <token>` ко всем вызовам API. При старте имеющийся токен проверяется через `GET /api/auth/me`. Кнопка **Выйти** очищает токен; любой `401` автоматически разлогинивает и возвращает на экран авторизации.

### Runtime-настройки графа (без перезапуска)

Адаптивные параметры можно менять на лету:

- **UI:** откройте вкладку **Graph Settings** во фронтенде, отредактируйте значения (включая чекбокс **On-topic guard**) и нажмите Save. В этой же вкладке есть секция **Observability**: ссылка на UI трейсинга Langfuse и живая сводка метрик бэкенда.
- **API:**
  - `GET /api/graph/settings` → текущие значения (включая `TOPIC_GUARD_ENABLED`).
  - `PUT /api/graph/settings` с JSON-телом любого подмножества `COOLDOWN_SOLVES`, `MAX_REGEN_ATTEMPTS`, `MASTERY_SUCCESS_STREAK`, `ADVANCED_SUCCESS_STREAK` (положительные целые, валидируются) и/или `TOPIC_GUARD_ENABLED` (булево) → сохраняет в Postgres, обновляет Redis-кеш и возвращает новые значения. Изменения применяются сразу на следующем ходу графа — например, переключение `TOPIC_GUARD_ENABLED` включает/выключает гард в рантайме без перезапуска.

### On-topic guardrail (настраивается в рантайме)

Узел `topic_guard` ([`backend/app/graph/nodes/topic_guard.py`](backend/app/graph/nodes/topic_guard.py:1)) удерживает чат в рамках программирования и текущего процесса обучения. Он сочетает быструю эвристику по ключевым словам/контексту с LLM-классификатором для неоднозначных случаев и работает **fail-open**: при недоступности LLM по умолчанию считает запрос on-topic (с логированием), чтобы обучение не блокировалось. Запросы не по теме получают вежливый отказ (без RAG и без исполнения); отправка кода всегда on-topic. Отключить можно, выставив `TOPIC_GUARD_ENABLED=false` (env seed) либо через UI Graph Settings / `PUT /api/graph/settings` в рантайме.

### Секции / тематики (сайдбар)

Левый сайдбар показывает **человекочитаемые секции (тематики)** вместо сырых строк `skill_id`. Сид заполняет **по 20 человекочитаемых секций на язык** (Python и JavaScript) — первые 15 повторяют концепции skill-графа (переменные, IO, условия, циклы, функции, …), плюс 5 доменных тематик (анализ данных, веб-скрейпинг, async, …) — и студенты могут **добавлять свои**. Выбор секции — новый способ задать **тематику (topic)**: это **НОВАЯ ось, ортогональная `language` и дополняющая `skill`/`concept`**:

- `language` (python | javascript) — по-прежнему исполняемая цель. Без изменений.
- `current_skill` / `concept` — по-прежнему педагогическая ось, по которой идёт адаптивный цикл. Без изменений.
- **секция → `topic`** — выбор секции задаёт per-user `topic` (`topic`/название секции), что меняет *оформление* (flavour) сгенерированных задач + поисковых запросов. Переключение секции **не сбрасывает прогресс** и **не** портит skill-граф. Пустая тематика = ровно то нейтральное поведение, что и сегодня.

Бэкенд: SQLAlchemy-модели `Section` и `RemediationLink` находятся в [`backend/app/db/models.py`](backend/app/db/models.py:1); столбец `users.current_section_id` добавляется идемпотентным паттерном `ALTER TABLE … ADD COLUMN IF NOT EXISTS` при старте в [`backend/app/main.py`](backend/app/main.py:1). Засев выполняет [`backend/app/seed/sections.py`](backend/app/seed/sections.py:1) (`seed_sections()`, `seed_links()`), а «пол» ссылок — [`backend/app/seed/content/curated_links.py`](backend/app/seed/content/curated_links.py:1). Per-user `topic` (`users.topic`) по-прежнему сохраняется и прокидывается через `run_turn`.

- **UI:** **панель секций** в сайдбаре — выпадающий список языка `<select>` (его переключение динамически перезагружает секции этого языка и управляет языком редактора), **динамическое поле фильтра**, **кликабельные карточки секций**, текущая секция **закреплена сверху и подсвечена цветом**, на каждой карточке **пиктограмма «?»**, отправляющая в чат вводные статьи/видео, и форма **«+ Добавить секцию/тематику»** с инлайн-валидацией 400/409. Прежняя строка **«Theme»** удалена из тулбара редактора кода (тематикой теперь управляет сайдбар).
- **API** ([`backend/app/api/sections.py`](backend/app/api/sections.py:1), все защищены auth, `user_id` из JWT):
  - `GET /api/languages` → `{"languages":[{"id":"python","label":"Python"},{"id":"javascript","label":"JavaScript"}]}`.
  - `GET /api/sections?language=...` → список (глобальные засеянные + собственные пользователя) с флагами `is_current` + `current_section_id`.
  - `POST /api/sections` → создать секцию пользователя (заголовок ≤120 символов; **400** невалидно, **409** дубликат).
  - `POST /api/sections/select` → задаёт тематику пользователя из секции, сохраняет `current_section_id` и **выполняет свежий ход графа, который отменяет ранее выданную задачу и порождает НОВУЮ тематическую задачу** (повторяет форму ответа `/api/chat` с `state.current_task_id`, `state.cancelled_task_id`, `state.topic`, `state.current_section_id`). Это исправляет прежний баг, когда смена тематики печатала сообщение, но не порождала новую задачу.
  - `POST /api/sections/{id}/intro` (пиктограмма «?») → возвращает ≥4 проверенные вводные ссылки (статьи) + ≥1 видео по концепции секции и выбранному языку.
- **Паритет WebSocket** ([`backend/app/api/ws.py`](backend/app/api/ws.py:1)): `{type:"select_section"}` и `{type:"section_intro"}` повторяют REST-вызовы.

Прежний свободный **topic API** остаётся доступным (теперь в основном управляется выбором секции): `GET /api/topic` → `{ "topic": str }`; `PUT /api/topic` → задать/очистить (auth; сохраняет `users.topic`; **400**, если длиннее 120 символов); `GET /api/topics` → `{ "topics": [str] }` (предлагаемые темы). Ходы WebSocket по-прежнему принимают опциональный `topic`, а удобное сообщение `{type:"topic", topic}` отвечает `{type:"topic_ok"}`.

### Интернет-задачи (LLM-генерация + проверка в песочнице)

Помимо подготовленного контента, тьютор может **сгенерировать свежую задачу на лету** с помощью LLM ([`backend/app/tasks/generator.py`](backend/app/tasks/generator.py:1)):

1. **(Опц.) веб-привязка:** когда задана `topic`, веб-поиск собирает 2–3 сниппета, чтобы задача выглядела актуальной/реалистичной (fail-open — пропускается, если пусто).
2. **LLM-генерация:** `chat_json` возвращает строгий payload задачи (условие, `entry_point`, `reference_solution`, видимые + скрытые тесты, сложность, concept) — чистая функция, без I/O, с темой `topic`.
3. **Проверка в песочнице:** сгенерированное **эталонное решение запускается на всех тестах** в `code-executor`; при неудаче ошибка передаётся обратно в LLM (reflection loop с ограничением `MAX_REGEN_ATTEMPTS`), пока не пройдёт — та же гарантия отсутствия галлюцинаций, что и у подготовленных задач.
4. **Сохранение + выдача:** проверенная задача сохраняется в динамическом сторе ([`backend/app/tasks/dynamic_store.py`](backend/app/tasks/dynamic_store.py:1)) (in-process кеш **плюс** таблица Postgres `GeneratedTask` для устойчивости к рестартам/воркерам), помечается `task_source="generated"` с id `gen_<uuid>` и становится резолвимой через `get_task(task_id)` для следующего **Run & Check**.

Генерация всегда **привязана к текущему навыку/concept**, выбранному адаптивным циклом, поэтому траектория сохраняется; `topic` меняет только оформление. Весь путь **fail-open** — если генерация/проверка не удаётся после ретраев, возвращается `None`, и тьютор откатывается на подготовленные `tasks_for_skill(...)`. Управляется мастер-переключателем **`INTERNET_TASKS_ENABLED`** (по умолчанию `true`; `false` для режима «только подготовленные») и свойством конфигурации `search_enabled`.

### Веб-поиск (SearXNG + MCP-сервер)

Веб-поиск обеспечивает и ссылки/выдержку для remediation на пути неудачи, и (опциональную) привязку сгенерированных задач. Его дают два отдельных контейнера, оба полностью **опциональны / fail-open**:

- **`searxng`** — self-hosted инстанс мета-поиска [SearXNG](https://github.com/searxng/searxng), образ **`searxng/searxng:2026.5.31-7159b8aed`**. Настраивается через [`searxng/settings.yml`](searxng/settings.yml:1) с **включённым форматом вывода JSON** (нужен для программного парсинга) и небольшим набором движков без API-ключей (duckduckgo, bing, brave, wikipedia). Только внутренний в сети compose (по умолчанию без публикуемого порта хоста); использует том `searxngdata`.
- **`searxng-mcp`** — крошечный **встроенный в репозиторий** Python MCP-сервер ([`searxng-mcp/server.py`](searxng-mcp/server.py:1), образ `demo_ai_agent-searxng-mcp:latest`), предоставляющий единственный инструмент **`web_search`** поверх **Streamable HTTP** на `http://searxng-mcp:8077/mcp` (health на `/health`). Он читает `SEARXNG_URL` и нормализует результаты в `{title, url, snippet}`. Зависит от `searxng: service_healthy`.

Поисковый клиент бэкенда ([`backend/app/search/`](backend/app/search/__init__.py:1)) сначала пробует **MCP** ([`mcp_client.py`](backend/app/search/mcp_client.py:1)), затем откатывается на **прямой SearXNG JSON** ([`searxng_client.py`](backend/app/search/searxng_client.py:1)), затем на пустой результат — и **никогда не выбрасывает исключение** вызывающему коду. `GET /api/search/health` сообщает о доступности `{mcp, searxng}` для диагностики. Новая зависимость `mcp==1.12.4` (в [`requirements.txt`](requirements.txt:1)) обеспечивает MCP-клиент бэкенда и образ MCP-сервера.

> **Живые веб-результаты требуют исходящего egress** к вышестоящим движкам (bing / duckduckgo / brave / wikipedia). В средах с заблокированным egress SearXNG может возвращать пустые результаты — система остаётся **работоспособной** и деградирует плавно (засеянный «пол» link store всё равно даёт ≥4 ссылки, объяснение только от LLM, подготовленные задачи). Это зеркалит уже существующее примечание про офлайн-Langfuse.

### RAG link store (сохранение, доступность, удаление, гарантия ≥4 ссылок)

Прагматичный реляционный **link store** ([`backend/app/rag/link_store.py`](backend/app/rag/link_store.py:1)) сохраняет сгенерированные/найденные ссылки remediation и intro в таблицу `remediation_links`, чтобы они **переиспользовались между студентами**, а не запрашивались заново на каждом ходу.

- **Сохранение.** Узел `web_search` ([`backend/app/graph/nodes/web_search.py`](backend/app/graph/nodes/web_search.py:1)) и поток intro «?» сохраняют каждую ссылку (url, title, snippet, language, `error_type`/`concept`, `kind` = `remediation`|`intro`) в стор по уникальному ключу `(url, error_type, language)`.
- **Проверка доступности.** Во время выдачи показываемые ссылки проверяются конкурентным HTTP-запросом **`HEAD`** (таймаут ≤4с, с редиректами, **fail-open**): сетевая ошибка помечает ссылку «мёртвой» для этой выдачи и увеличивает счётчик неудач, но никогда не выбрасывает исключение в ход графа.
- **Замена «мёртвых» ссылок.** Ссылка, не прошедшая проверку, исключается из ответа и **заменяется через веб-поиск**; реальный `web_search` инъектируется при старте через `set_replacement_search(...)` в [`backend/app/main.py`](backend/app/main.py:1), а вновь найденные ссылки сохраняются обратно в стор.
- **Правило удаления.** Ссылка, которая **не открывается более 50 раз в скользящем 3-дневном окне**, **удаляется** из стора (`record_failure`, `FAIL_THRESHOLD=50`, `FAIL_WINDOW=3 days`). Удаление выполняется лениво при неудачных проверках — фоновый процесс не нужен.
- **Гарантия ≥4 ссылок.** `get_verified_links(..., min_links=4)` гарантирует, что **каждое объяснение ошибки содержит ≥4 проверенные ссылки**, комбинируя сохранённые + живые + засеянные источники. Офлайн-**засеянный «пол»** (≥4 статьи + ≥1 видео на концепцию/язык в [`backend/app/seed/content/curated_links.py`](backend/app/seed/content/curated_links.py:1), засевается через `seed_links()`) держит гарантию даже без egress.
- **Переиспользование / повторная индексация.** Сгенерированные или найденные задачи сохраняются для переиспользования, а существующие per-student `task_serve_history` + cooldown уникальности гарантируют, что студент никогда не увидит одну и ту же задачу дважды. Повторная RAG-индексация теперь возможна — `ingest_all` больше не делает жёсткий ранний возврат; она управляется `force`/`RAG_REINGEST` ([`backend/app/rag/ingestion.py`](backend/app/rag/ingestion.py:1)) — поэтому новые секции и вводные/remediation ссылки можно засеять в RAG/link store при старте.

### UX фронтенда (сайдбар, сплиттер, чат)

- **Сворачиваемый сайдбар** — переключатель ◀/▶ (`.sidebar-toggle`, `.sidebar.collapsed`), состояние которого сохраняется в `localStorage`.
- **Панель секций** — выпадающий список языка `<select>` (управляет языком редактора), **динамическое поле фильтра**, **кликабельные карточки секций** (`.sections-panel`, `.section-card`), текущая секция **закреплена сверху и подсвечена цветом** (`.section-card.current`), на каждой карточке **пиктограмма «?»** (`.section-help`), отправляющая в чат вводные статьи/видео, и форма **«+ Добавить секцию/тематику»** с инлайн-валидацией 400/409. Прежняя строка **«Theme»** в тулбаре редактора удалена.
- **Прокрутка чата** — чат **больше не прокручивается автоматически** при новых сообщениях ассистента/системы; вместо этого появляется **бейдж счётчика непрочитанных + плавающая кнопка со стрелкой вниз для прокрутки в конец** (`.scroll-bottom-btn`, `.unread-badge`), клик по которой плавно прокручивает к последнему сообщению. Собственные отправленные пользователем сообщения по-прежнему прокручиваются вниз.
- **Без статусных сообщений «Sandbox»** — статусные сообщения `🧪 Sandbox: …` больше не показываются в чате (pass/fail уже отражается в ответе ассистента).
- **Перетаскиваемый сплиттер** — `.splitter` (`col-resize`) между панелями чата и редактора кода позволяет менять их размер; разделение ограничено (25–70%) и сохраняется в `localStorage`.
- **Новые функции `api.js`** — `getLanguages`, `getSections`, `createSection`, `selectSection`, `getSectionIntro` ([`frontend/src/api.js`](frontend/src/api.js:1)).

### Трейсинг Langfuse (включён из коробки)

Трейсинг работает без ручной настройки: `docker-compose` автоматически создаёт организацию, проект, дефолтного пользователя **admin** и API-ключи проекта в Langfuse и пробрасывает **те же ключи** в бэкенд (`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`), поэтому `langfuse_enabled=True` с первого запуска. Прогоны графа (узлы, включая `topic_guard`, плюс вызовы LLM) появляются в UI Langfuse под проектом **tutor-project**.

Сервис `langfuse` также выставляет `LANGFUSE_UI_RELEASE_CHECK_ENABLED=false` (рядом с `TELEMETRY_ENABLED=false`) в `docker-compose.yml`, чтобы отключить встроенную проверку релизов/обновлений Langfuse. В офлайн-окружении или среде с заблокированным egress эта проверка не может достучаться до внешних GitHub-релизов и постоянно логирует некритичные ошибки `tRPC route failed on public.checkUpdate: Internal error` / `Failed to fetch or json parse the latest releases`; её отключение оставляет логи чистыми и не влияет на трейсинг.

- **UI Langfuse / вход admin:** http://localhost:3001 — email `admin@example.com`, пароль `qwerty123456` (имя пользователя `admin`). Переопределяется переменными `LANGFUSE_INIT_USER_*` в `.env`.
  > **Если вход admin не работает** (например, после изменения переменных `LANGFUSE_INIT_*`): эти переменные применяются Langfuse **только при первом старте с пустой базой** `langfuse-db`. На уже инициализированном томе они игнорируются. Выполните `docker compose down -v` (удалит том `langfusedbdata`) и затем `docker compose up -d` — INIT отработает на чистой БД, и пользователь admin будет создан заново.
- **Отключить трейсинг:** сделайте `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` бэкенда пустыми (и очистите дефолты в compose). Тогда бэкенд работает нормально и никогда не падает из-за Langfuse.

### Метрики бэкенда

`GET /api/metrics/summary` возвращает живые агрегаты из БД приложения: число пользователей, суммарные решения, попытки, число успехов/неудач, долю успеха, средний mastery, число выданных заданий, распределение по состояниям навыков и по типам ошибок, плюс статус/ссылку Langfuse. Они дополняют пер-трейсовые метрики latency/объёма/ошибок, которые уже даёт Langfuse. Сводка отображается во вкладке фронтенда **Graph Settings → Observability**.

4. Попробуйте сквозной сценарий: введите *I want to learn Python loops*, получите задачу, напишите решение в редакторе Monaco, нажмите **Run & Check**. Каждая отправка несёт свой `task_id`, поэтому проверяется против правильной задачи даже при отсутствии состояния чекпойнта. Неверный ответ запускает видеоразбор + **≥4 проверенные ссылки из веб-поиска и краткое объяснение** + *похожую* задачу (проваленная задача **не** переформулируется); прохождение подтверждается без переформулирования решённой задачи и явно **предлагает следующую задачу** (`➡️ Следующая задача`). Выберите **секцию/тематику** в сайдбаре, чтобы сразу получить свежую тематическую интернет-задачу (и нажмите её **«?»** для вводного материала). Простой теоретический вопрос возвращает объяснение плюс follow-up практическое упражнение.

### Чистая пересборка (`docker compose down -v`)

Чтобы пересобрать с нуля (проверенный путь): `docker compose down -v` удаляет именованные тома — теперь включая новый **`searxngdata`** наряду с `pgdata`, `qdrantdata` и `langfusedbdata` — затем пересоберите образы через buildx-сборщик `dnsbuilder` (который теперь также собирает **`demo_ai_agent-searxng-mcp:latest`**) и `docker compose up -d`. Это и была проверенная пересборка: все сервисы поднялись Up/healthy, и `curl http://localhost:8000/api/search/health` вернул `{"mcp":true,"searxng":true}`.

> **Примечание:** На хостах, где песочница Docker-сборки нормально резолвит DNS (npm/PyPI), достаточно стандартного `docker compose up --build` (DNS-сборщик не нужен). `docker-compose.yml` фиксирует имена `image:`, которые производит шаг buildx, поэтому после сборки образы переиспользуются командой `docker compose up` без пересборки.

> **Примечание:** Адаптивная петля и sandbox-гарантия кода работают end-to-end даже без реального LLM-ключа (graceful degradation — placeholder-ключ приводит к локальному fallback эмбеддингов, и граф не падает).

> Система деградирует плавно: если эндпоинт эмбеддингов недоступен, используется детерминированный локальный fallback, а если не удаётся инициализировать checkpointer на Postgres, происходит откат на in-memory checkpointer — так что демо всё равно работает.

---

## 5. Граничные случаи и как они обрабатываются

1. **Неполные данные о цели** — студент пишет *I want to learn*. **Goal Planner** использует LangGraph `interrupt` (human-in-the-loop), чтобы спросить, какой язык и цель, вместо того чтобы догадываться. UI показывает вопрос, а ответ возобновляет граф.
2. **Ошибки внешних API** — вызовы LLM/эмбеддингов/RapidAPI обёрнуты в **retry с экспоненциальной задержкой** (`tenacity`). Если **RapidAPI** падает во время выполнения, фабрика исполнителей прозрачно **откатывается на локальный исполнитель**. Если **LLM** недоступен, агент возвращает дружелюбное сообщение, а состояние сессии сохраняется для последующего возобновления.
3. **Неоднозначный запрос** — **Intent Router** возвращает оценку уверенности; ниже порога он направляет к узлу **Clarify** и просит студента уточнить, вместо того чтобы выбирать путь наугад.
4. **Таймаут кода студента (бесконечный цикл)** — песочница применяет **жёсткий лимит по реальному времени (wall-clock)** и ограничение по памяти; результат отмечается как `timed_out`, упрощённый трейс объясняет вероятный бесконечный цикл, и тьютор направляет на remediation в том же порядке блоков (трейс → Explanation+ссылки → похожая задача).
5. **Конфликтующие инструкции** — студент просит *just give me the answer* во время активной задачи. **Guardrail** в Answer Generator отказывает в полном решении и возвращает **подсказки**, объясняя педагогическую причину.
6. **Веб-поиск / MCP недоступны** — поисковый клиент **fail-open**: если **MCP-сервер** недоступен, он откатывается на **прямой SearXNG JSON**; если **SearXNG** недоступен (или egress заблокирован и он ничего не возвращает), используется **засеянный «пол»** link store, поэтому ≥4 ссылки всё равно показываются рядом с объяснением только от LLM. Бэкенд `depends_on` поиск только с `condition: service_started`, поэтому весь стек поднимается и работает без поиска.
7. **Генерация задачи не проходит проверку** — если эталонное решение только что сгенерированной задачи не проходит все sandbox-тесты в пределах `MAX_REGEN_ATTEMPTS`, генерация ничего не возвращает, и тьютор прозрачно **откатывается на подготовленную задачу** для того же навыка — поэтому сломанная сгенерированная задача никогда не выдаётся.
8. **Отправлен не-код / мусор / синтаксически невалидный код** — `detect_input_issue` ([`backend/app/graph/nodes/_error_utils.py`](backend/app/graph/nodes/_error_utils.py:1)) распознаёт пустую отправку, `SyntaxError` (Python — через `compile()`, с точной строкой/столбцом и неправильными символами) и текст-прозу вместо кода; разбор прямо говорит «это не {язык}-код / вы ничего не отправили» и указывает на проблемное место, при этом всё равно проходит через remediation (ссылки + пример правильного решения + похожая задача). Для answer-типов (`predict_output`/`trace_value`) детект пропускается — там легитимно вводится значение, а не код.
9. **«Мёртвые» / хронически нерабочие ссылки remediation** — во время выдачи link store ([`backend/app/rag/link_store.py`](backend/app/rag/link_store.py:1)) проверяет доступность каждой ссылки (конкурентный HTTP `HEAD`, таймаут ≤4с, **fail-open**). «Мёртвая» ссылка отбрасывается и **заменяется через веб-поиск** для этого ответа; её счётчик неудач увеличивается, а ссылка, которая **не открывается более 50 раз в скользящем 3-дневном окне**, **удаляется** из стора. Гарантия ≥4 ссылок по-прежнему держится за счёт засеянного «пола», поэтому объяснение никогда не опускается ниже четырёх рабочих ссылок, даже когда отдельные URL «протухают».

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
- **PostgreSQL** — профиль пользователя (включая per-user `topic` и `current_section_id`), прогресс по навыкам, попытки, **`task_serve_history`** (cooldown уникальности), таблица **`sections`** (человекочитаемые тематики сайдбара, засеянные + созданные пользователем), link store **`remediation_links`** (сохранённые ссылки remediation/intro со счётчиками здоровья для доступности + удаления), таблица устойчивости **`generated_tasks`** для интернет-задач и **LangGraph checkpointer**.
- **Redis** — сессии, очередь песочницы, rate limiting и **кеш runtime-настроек графа** (`graph:settings`, источник истины — Postgres).
- **Langfuse (self-hosted, опционально)** — наблюдаемость/трейсинг LangGraph через `CallbackHandler`, с **собственным отдельным Postgres** (`langfuse-db`). UI на http://localhost:3001; включается только при заданных ключах, иначе трейсинг пропускается без влияния на бэкенд. Сервис запускается с `LANGFUSE_UI_RELEASE_CHECK_ENABLED=false`, чтобы подавить шумные, но некритичные ошибки `checkUpdate` в офлайн-окружениях или средах с заблокированным egress.
- **Контейнер code-executor** — изолированная локальная песочница (Python + Node) с лимитами по времени/памяти и эфемерной файловой системой. Отправки несут свой `task_id`, поэтому **Run & Check** проверяется против правильной задачи даже при отсутствии состояния чекпойнта.
- **RapidAPI CodeRunner** (опционально) — онлайн-исполнение кода при наличии конфигурации; фабрика откатывается на локальный при сбое.
- **SearXNG (self-hosted, опционально)** — self-hosted инстанс мета-поиска (образ `searxng/searxng:2026.5.31-7159b8aed`, конфигурация в [`searxng/settings.yml`](searxng/settings.yml:1) с включённым выводом JSON), используемый для ссылок remediation и привязки генерации интернет-задач. Только внутренний в сети compose; **fail-open** (тьютор работает и без него). Живые результаты требуют исходящего egress к вышестоящим движкам.
- **SearXNG MCP server (в репозитории, опционально)** — крошечный Python MCP-сервер ([`searxng-mcp/server.py`](searxng-mcp/server.py:1)), предоставляющий инструмент `web_search` поверх Streamable HTTP на `http://searxng-mcp:8077/mcp`; он связывает MCP-клиент бэкенда с SearXNG. Поисковый клиент бэкенда ([`backend/app/search/`](backend/app/search/__init__.py:1)) пробует MCP → прямой SearXNG JSON → пусто (никогда не выбрасывает исключение). Использует `mcp==1.12.4`.
- **Подготовленные документы** — заметки по теории, задачи по программированию (условие + видимые/скрытые тесты + проверенное в песочнице эталонное решение) и видеоразборы (с URL и тайм-кодами), заполняемые в [`backend/app/seed/content/curated.py`](backend/app/seed/content/curated.py:1). У каждого засеянного навыка в обоих языках есть хотя бы одно проверенное в песочнице задание `practice` (34/34 задания проходят свои видимые + скрытые тесты), поэтому у выбора навыка с учётом контента всегда есть реальная задача для выдачи.
- **Секции и засеянный «пол» ссылок** — по 20 человекочитаемых секций на язык, засеваемых [`backend/app/seed/sections.py`](backend/app/seed/sections.py:1) (`seed_sections()`), плюс вводный/remediation **«пол» ссылок** (≥4 статьи + ≥1 видео на концепцию/язык) в [`backend/app/seed/content/curated_links.py`](backend/app/seed/content/curated_links.py:1), засеваемый в стор `remediation_links` через `seed_links()`. Link store ([`backend/app/rag/link_store.py`](backend/app/rag/link_store.py:1)) переиспользует, проверяет доступность, заменяет и удаляет эти ссылки, гарантируя **≥4 проверенные ссылки** на каждое объяснение даже офлайн.
- **Интернет-задачи (сгенерированные)** — задачи, генерируемые на лету LLM ([`backend/app/tasks/generator.py`](backend/app/tasks/generator.py:1)), опционально привязанные к веб-поиску, с автоматически сгенерированными тестами. Они **проверяются в песочнице** (эталонное решение должно пройти все тесты) до выдачи, сохраняются в динамическом сторе ([`backend/app/tasks/dynamic_store.py`](backend/app/tasks/dynamic_store.py:1)) + таблице `generated_tasks` и проходят через тот же cooldown уникальности.

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
| 7 | Полное покрытие заданиями (каждый засеянный навык, оба языка) + выбор навыка/задания с учётом контента, чтобы новый пользователь всегда получал настоящую задачу | [`backend/app/seed/content/curated.py`](backend/app/seed/content/curated.py:1), [`backend/app/graph/nodes/skill_path.py`](backend/app/graph/nodes/skill_path.py:1), [`backend/app/graph/nodes/task_selector.py`](backend/app/graph/nodes/task_selector.py:1) |
| 8 | Самоописывающиеся отправки (`task_id` прокидывается end-to-end), чтобы **Run & Check** проверялся надёжно | [`backend/app/api/routes.py`](backend/app/api/routes.py:1), [`backend/app/graph/runner.py`](backend/app/graph/runner.py:1), [`frontend/src/api.js`](frontend/src/api.js:1) |
| 9 | Де-дупликация Run & Check: успех = без переформулирования + явное предложение следующей задачи; неудача = **code-grounded разбор по реально присланному коду/вводу** (детект не-кода/SyntaxError) с примером правильного решения и целевыми ссылками, в строгом порядке **трейс → Explanation+ссылки → похожая задача**; вариативность задач через `exercise_type` + ротацию типов | [`backend/app/graph/nodes/code_validator.py`](backend/app/graph/nodes/code_validator.py:1), [`backend/app/graph/nodes/_error_utils.py`](backend/app/graph/nodes/_error_utils.py:1), [`backend/app/graph/nodes/web_search.py`](backend/app/graph/nodes/web_search.py:1), [`backend/app/graph/nodes/remediation.py`](backend/app/graph/nodes/remediation.py:1), [`backend/app/graph/nodes/task_selector.py`](backend/app/graph/nodes/task_selector.py:1), [`backend/app/execution/base.py`](backend/app/execution/base.py:1), [`backend/app/graph/nodes/adaptivity.py`](backend/app/graph/nodes/adaptivity.py:1) |
| 10 | Интернет-задачи через живую LLM-генерацию + веб-поиск, проверенные в песочнице; `INTERNET_TASKS_ENABLED` | [`backend/app/tasks/generator.py`](backend/app/tasks/generator.py:1), [`backend/app/tasks/dynamic_store.py`](backend/app/tasks/dynamic_store.py:1), [`backend/app/db/models.py`](backend/app/db/models.py:1) (`GeneratedTask`) |
| 11 | Бэкенд веб-поиска = SearXNG + SearXNG MCP server (Streamable HTTP `web_search`), fail-open MCP → прямой → пусто; `GET /api/search/health` | [`searxng/settings.yml`](searxng/settings.yml:1), [`searxng-mcp/server.py`](searxng-mcp/server.py:1), [`backend/app/search/`](backend/app/search/__init__.py:1), [`docker-compose.yml`](docker-compose.yml:64) |
| 12 | Переключение тематики (`topic` ортогональна языку/навыку); `GET/PUT /api/topic`, `GET /api/topics` | [`backend/app/api/routes.py`](backend/app/api/routes.py:1), [`backend/app/db/models.py`](backend/app/db/models.py:1) (`users.topic`), [`frontend/src/App.jsx`](frontend/src/App.jsx:1) |
| 13 | Секции/тематики сайдбара: по 20 человекочитаемых секций на язык + создаваемые пользователем; кликабельные карточки, фильтр, выпадающий список языка, закреплённая текущая, intro «?»; выбор секции отменяет старую задачу + генерирует НОВУЮ тематическую задачу; `GET /api/languages`, `GET/POST /api/sections`, `POST /api/sections/select`, `POST /api/sections/{id}/intro` + паритет WS | [`backend/app/api/sections.py`](backend/app/api/sections.py:1), [`backend/app/api/ws.py`](backend/app/api/ws.py:1), [`backend/app/db/models.py`](backend/app/db/models.py:1) (`Section`, `users.current_section_id`), [`backend/app/seed/sections.py`](backend/app/seed/sections.py:1), [`backend/app/graph/nodes/task_selector.py`](backend/app/graph/nodes/task_selector.py:1), [`frontend/src/api.js`](frontend/src/api.js:1) |
| 14 | RAG link store: сохранение + переиспользование, проверка доступности при выдаче, замена «мёртвых» ссылок, удаление при >50 неудачах за 3 дня, гарантия ≥4 проверенных ссылок с офлайн-засеянным «полом» | [`backend/app/rag/link_store.py`](backend/app/rag/link_store.py:1), [`backend/app/db/models.py`](backend/app/db/models.py:1) (`RemediationLink`), [`backend/app/seed/content/curated_links.py`](backend/app/seed/content/curated_links.py:1), [`backend/app/graph/nodes/web_search.py`](backend/app/graph/nodes/web_search.py:1), [`backend/app/graph/nodes/remediation.py`](backend/app/graph/nodes/remediation.py:1), [`backend/app/rag/ingestion.py`](backend/app/rag/ingestion.py:1) |
