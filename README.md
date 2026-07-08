# project-memory-kit

English version: [README.en.md](README.en.md)

Версионные изменения: [CHANGELOG.md](CHANGELOG.md)

`project-memory-kit` добавляет в репозиторий локальную память для coding agents. Она хранит контекст проекта рядом с кодом: файлы, символы, импорты, обратные зависимости, релевантные тесты, прошлые сбои, исследования и причины принятых решений.

Главная цель простая: несколько чатов могут работать над одним проектом и не терять зависимый контекст.

## Что устанавливается

Профили:

- `Codex`: `AGENTS.md`, `.agents/skills/`, `.project-memory/`, `tools/project_memory/`, `pmem`.
- `Claude`: `CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/commands/`.
- `Multi-agent`: общие роли, правила и задачи для нескольких агентов, плюс Codex и Claude инструкции.

Если `AGENTS.md` или `CLAUDE.md` уже есть, installer сохраняет пользовательский текст и обновляет только managed-блок:

```text
<!-- PMEM:BEGIN -->
...
<!-- PMEM:END -->
```

Внешние skills не управляются этим проектом. Их можно ставить отдельно и описывать правила использования в `AGENTS.md` или `CLAUDE.md`.

## Установка

В корне проекта:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

npm/npx вариант:

```bash
npx --yes --package github:AnKu304/project-memory-kit pmem init --target .
```

Интерактивная установка:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --interactive
```

Wizard спросит профиль агента, task templates, Human layer, vector backend и MCP config. Команды без `--interactive` работают как раньше.

Выбор профиля:

```bash
pmem init --target . --agent codex
pmem init --target . --agent claude
pmem init --target . --agent multiagent
```

Проверка после установки:

```bash
./pmem doctor
./pmem index --mode full
```

## Обновление

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent auto
```

Upgrade обновляет managed-файлы и запускает migrations. Базы, логи и runtime state в `.project-memory/` сохраняются.

Профиль можно добавить при обновлении:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent claude
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent multiagent
```

## Рабочий цикл агента

Перед правками:

```bash
./pmem doctor
./pmem tasks check
./pmem impact --base HEAD --format markdown
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
./pmem context --task "<task>" --base HEAD --compiled --out .project-memory/reports/COMPILED_CONTEXT.md
```

Контекст ограничивается короткими выдержками, id и путями к полной записи. Большие файлы, логи и отчеты проверяются локальными командами; в модель передается только нужный итог или короткий фрагмент.

`./pmem index --mode changed` перед правкой запускается только когда `./pmem status` показывает stale/missing файлы в зоне задачи, контекст выглядит неполным или меняются общие маршруты, API-контракты, схемы, зависимости, тесты или архитектура.

После правок:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

Если тест упал:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
```

## Мультичатовая работа

Несколько чатов могут читать память параллельно. Команды записи проходят через короткую локальную блокировку, чтобы не повредить состояние SQLite/Qdrant:

- чтение: `status`, `search`, `context`, `impact`, `tests`, `knowledge context`, `rationale context`;
- запись: `index`, `knowledge add/update/retire`, `rationale add/update/retire`, `record-failure`, `human export/sync/graph`, `tasks close/import`, `modules set`.

Если память занята другим чатом, команда записи ждет `concurrency.write_lock.timeout_seconds`. Если блокировка не освободилась, команда попадает в локальную очередь:

```bash
./pmem lock status
./pmem lock clear
./pmem queue list
./pmem queue drain
```

`lock clear` удаляет только устаревшие блокировки. `lock clear --force` нужен только если вы уверены, что процесс записи уже остановлен.

`watch --serve` не держит глобальную блокировку между проверками. Если автоиндексация видит активную запись из другого чата, она быстро пропускает текущий проход и использует уже существующий индекс.

Индексация и audit обходят проект pruned walker-ом: ignored-директории вроде `node_modules/`, `.project-memory/`, `.playwright-cli/`, `.playwright-mcp/`, `.turbo/` и `coverage/` отсекаются до входа внутрь.

## Основные команды

Installer:

```bash
pmem init --target .
pmem init --target . --interactive
pmem install --target .
pmem upgrade --target . --agent auto
pmem upgrade --target . --with-vector
pmem uninstall --target . --keep-memory
pmem version
```

В установленном проекте:

```bash
./pmem doctor
./pmem status
./pmem report
./pmem impact --base HEAD --format markdown
./pmem context --task "описание задачи"
./pmem context --task "описание задачи" --compiled
./pmem search --query "payment validation" --limit 10
./pmem search --query "payment validation" --limit 10 --debug
./pmem tests --base HEAD
./pmem audit
./pmem audit --secrets
./pmem optimize
./pmem watch --serve --interval 5
./pmem lock status
./pmem queue list
./pmem queue drain
```

Задачи:

```bash
./pmem tasks check
./pmem tasks list
./pmem tasks close --file .agents/tasks/example.md --summary "Done"
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

Слои памяти:

```bash
./pmem knowledge add --type research --title "Resource mechanics" --file notes/research.md
./pmem knowledge update --id resource-mechanics --file notes/research.md
./pmem knowledge context --task "redesign product page"
./pmem rationale add --type decision --title "Use SQLite" --file notes/rationale/sqlite.md
./pmem rationale context --task "change memory database"
./pmem human export
./pmem human sync
./pmem human graph --html
```

MCP:

```bash
./pmem mcp --root .
./pmem mcp-config --root .
./pmem mcp-config --root . --client claude --write
```

## Слои памяти

Knowledge Layer

Слой знаний

Хранит исследования, архитектуру, SEO, дизайн, UX, продуктовые принципы и другие устойчивые знания проекта. Полные записи лежат в `.project-memory/knowledge/**/*.md`; в контекст обычно попадают только короткие выдержки и путь к полной версии.

Rationale Layer

Слой причинности

Хранит причины решений: выбранные подходы, отклоненные варианты, ошибки, эксперименты и инварианты. Запись должна опираться на проверяемые факты: тест, лог, diff, файл, failure или commit.

Human Layer

Человекочитаемый слой

Опциональный Obsidian-like слой. Он экспортирует current-записи `knowledge` и `rationale` в Markdown с frontmatter, backlinks и графом. По умолчанию выключен:

```bash
./pmem modules set human --enabled true
./pmem human export
./pmem human graph --html
```

Hybrid Search

Гибридный поиск

Поиск объединяет SQLite FTS5 `bm25()`, vector score, совпадения терминов, path, graph proximity, confidence, layer и recency. `./pmem search --debug` показывает компоненты ранжирования.

Vector Backend

Векторный backend

По умолчанию `backend: auto`: Qdrant/FastEmbed используются, если доступны; иначе включается deterministic fallback. Для managed runtime:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --with-vector
./pmem doctor
```

Для нескольких чатов можно указать локальный Qdrant-сервер в `.project-memory/config.yaml`:

```yaml
vector:
  backend: qdrant
  url: http://127.0.0.1:6333
```

Если `url` не задан, остается встроенный локальный Qdrant или fallback-режим. Встроенный Qdrant защищен короткой локальной блокировкой: если он занят другим процессом, `backend: auto` быстро использует SQLite/BM25 путь без долгого ожидания.

Context Compiler

Компилятор контекста

`./pmem context --compiled` собирает рабочий пакет задачи: local evidence, preflight/postflight gate, impact, ranked search, knowledge/rationale, lifecycle и provenance. Это основной режим для сложных задач, где важно не раздувать модельный контекст.

## MCP

`./pmem mcp` запускает локальный stdio MCP server поверх того же runtime и той же `.project-memory/` базы. Отдельная память не создается, данные во внешний сервис не отправляются.

MCP Task Write Tools

MCP-инструменты для записи задач

MCP умеет создавать, назначать и закрывать задачи в `.agents/tasks/`: `pmem_tasks_create`, `pmem_tasks_assign`, `pmem_tasks_close`. После записи задача переиндексируется локально.

## Версионные обновления

Кратко:

- `0.22.2`: Pruned Traversal Fix; status/index/context/audit skip ignored heavy directories before descent.
- `0.22.1`: Contention Fix; `watch --serve` no longer holds write-lock, auto-index skips when busy, embedded Qdrant is guarded with fast fallback.
- `0.22.0`: Multi-chat Write Concurrency; SQLite timeout, managed write lock, stale lock cleanup, write queue, Qdrant server URL.
- `0.21.0`: Depth Improvements; compiled context, retrieval diversity, golden evals, test graph bindings, lifecycle, local evidence, task gates, provenance.
- `0.20.0`: CI Runtime Warning Cleanup; GitHub Actions переведен на Node 24-capable actions и Node 22/24 matrix.
- `0.19.0`: MCP Task Write Tools; MCP может создавать, назначать и закрывать `.agents/tasks/`.
- `0.18.0`: Install Wizard; `pmem init --interactive` для выбора профиля и optional модулей.
- `0.17.0`: Human Graph Viewer; статический `human graph --html` для просмотра Human-графа.
- `0.16.0`: Memory Quality Dashboard; `pmem report` для локального Markdown/JSON отчета по состоянию памяти.
- `0.15.0`: TS/Next Graph Depth; route-to-component edges, client/server boundary и API route methods.
- `0.14.0`: Real File Watcher; локальный polling watcher по hash с явным `watch --serve`.
- `0.13.0`: Linear Sync; локальный bridge для экспорта/импорта задач Linear без обязательных зависимостей.
- `0.12.0`: Bidirectional Human Sync; двусторонняя синхронизация Human-слоя с conflict detection.

Полный список: [CHANGELOG.md](CHANGELOG.md)

## Разработка

Проверка этого репозитория:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests
npm run check
```
