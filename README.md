# project-memory-kit

English version: [README.en.md](README.en.md)

Версионные изменения: [CHANGELOG.md](CHANGELOG.md)

`project-memory-kit` добавляет в репозиторий локальную память для агентов, которые пишут код.

Память хранится внутри проекта, поэтому несколько чатов могут работать над одним кодом без потери контекста: агент видит файлы, символы, импорты, обратные зависимости, релевантные тесты, прошлые падения и смысловые правила проекта.

## Что появится в проекте

Профили установки:

- `Codex` по умолчанию: `AGENTS.md` и `.agents/skills/`.
- `Claude` опционально: `CLAUDE.md`, `.claude/rules/`, `.claude/skills/`, `.claude/commands/`.
- `Multi-agent` опционально: универсальная структура для нескольких агентов, плюс Codex и Claude инструкции.

Базовая структура Codex-профиля:

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
.project-memory/install.json
.project-memory/knowledge/
.project-memory/rationale/
.project-memory/evals/
tools/project_memory/
pmem
pmem.ps1
.gitignore
```

Claude-профиль добавляет:

```text
CLAUDE.md
.claude/settings.json
.claude/rules/project-memory.md
.claude/skills/dependency-graph-rag/
.claude/commands/pmem-context.md
.claude/commands/pmem-status.md
.claude/commands/pmem-audit.md
```

Multi-agent добавляет оба набора инструкций и роли:

```text
.agents/rules/
.agents/roles/
.agents/tasks/
.claude/agents/
```

Если `AGENTS.md` или `CLAUDE.md` уже есть, installer сохраняет пользовательский текст и обновляет только managed-блок:

```text
<!-- PMEM:BEGIN -->
...
<!-- PMEM:END -->
```

Внешние skills не управляются этим проектом. Их можно ставить отдельно и описывать правила их использования в `AGENTS.md` или `CLAUDE.md`.

## Установка

В корне проекта:

```bash
pipx run --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

npm/npx вариант:

```bash
npx --yes --package github:AnKu304/project-memory-kit pmem init --target .
```

Профиль выбирается флагом `--agent`:

```bash
# Codex по умолчанию
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .

# Claude
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --agent claude

# Multi-agent
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --agent multiagent
```

Чтобы точно взять свежий commit:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

С управляемым vector runtime:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target . --with-vector
```

Проверка:

```bash
./pmem doctor
./pmem index --mode full
```

## Обновление

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --agent auto
```

Upgrade обновляет managed-файлы и запускает migrations. Базы и runtime state в `.project-memory/` сохраняются.

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
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<task>" --base HEAD --reset-task --out .project-memory/reports/CHANGE_CONTEXT.md
```

Контекст ограничивается короткими выдержками, id и путями к полной версии. Агент должен сам проверять большие файлы, логи и отчеты локальными инструментами, а в рабочий контекст добавлять только релевантные выводы и короткие фрагменты. Полный текст открывается только если локальной выжимки недостаточно.

После правок:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

При падении теста:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
```

## Команды

Installer:

```bash
pmem init --target .
pmem init --target . --agent claude
pmem init --target . --agent multiagent
pmem install --target .
pmem upgrade --target . --agent auto
pmem upgrade --target . --with-vector
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
pmem version
```

В установленном проекте:

```bash
./pmem version
./pmem doctor
./pmem status
./pmem stale
./pmem migrate
./pmem modules list
./pmem modules set human --enabled true
./pmem modules set human --enabled false
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "описание задачи"
./pmem audit
./pmem audit --secrets
./pmem optimize
./pmem eval --file .project-memory/evals/search.jsonl
./pmem tasks check
./pmem tasks list
./pmem tasks close --file .agents/tasks/example.md --summary "Done"
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
./pmem human status
./pmem human export
./pmem human sync
./pmem human search --query "design rules"
./pmem human graph
./pmem knowledge add --type research --title "Resource mechanics" --file notes/research.md
./pmem knowledge update --id resource-mechanics --file notes/research.md
./pmem knowledge search --query "SEO rules"
./pmem knowledge conflicts
./pmem knowledge context --task "redesign product page"
./pmem knowledge show --id resource-mechanics
./pmem knowledge retire --id old-design-rules
./pmem rationale add --type decision --title "Use SQLite" --file notes/rationale/sqlite.md
./pmem rationale update --id use-sqlite --file notes/rationale/sqlite.md
./pmem rationale search --query "why not postgres"
./pmem rationale conflicts
./pmem rationale context --task "change memory database"
./pmem rationale show --id use-sqlite
./pmem rationale retire --id old-storage-choice
./pmem tests --base HEAD
./pmem tests --base HEAD --explain
./pmem search --query "payment validation" --limit 10
./pmem search --query "payment validation" --limit 10 --debug
./pmem search --query "pricing SEO" --layer knowledge
./pmem search --query "why sqlite" --layer rationale
./pmem search --query "design principles" --layer human
./pmem watch
./pmem watch --once
./pmem watch --interval 5 --max-runs 1
./pmem watch --serve --interval 5
./pmem record-failure --command "npm test" --log-file ".project-memory/logs/test.log"
./pmem mcp --root .
./pmem mcp-config --root .
./pmem mcp-config --root . --client claude --write
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

## Локальный MCP

`./pmem mcp` запускает локальный stdio MCP server поверх того же runtime и той же базы `.project-memory/`. Он не создает отдельную память и не отправляет данные во внешний сервис.

Пример подключения для MCP-клиента:

```toml
[mcp_servers.project_memory]
command = "/absolute/path/to/repo/pmem"
args = ["mcp", "--root", "/absolute/path/to/repo"]
```

Этот фрагмент можно вывести командой:

```bash
./pmem mcp-config --root .
./pmem mcp-config --root . --client claude --write
```

Доступные MCP tools:

```text
pmem_doctor
pmem_index
pmem_status
pmem_context
pmem_impact
pmem_tests
pmem_search
pmem_search_debug
pmem_eval
pmem_audit
pmem_modules
pmem_watch_status
pmem_tasks
pmem_human_status
pmem_human_export
pmem_human_search
pmem_human_graph
pmem_knowledge_context
pmem_knowledge_search
pmem_knowledge_show
pmem_rationale_context
pmem_rationale_search
pmem_rationale_show
pmem_record_failure
```

MCP удобен для коротких structured-ответов агенту. CLI-команды остаются базовым способом проверки и fallback, если MCP-клиент не настроен.

## Как работает

- SQLite хранит граф проекта: файлы, символы, chunks, imports, calls, inheritance, failures.
- Knowledge layer хранит исследования, архитектуру, SEO, дизайн, UX, продуктовые механики и другие проектные принципы.
- Полные версии knowledge-записей лежат в `.project-memory/knowledge/**/*.md`; SQLite хранит метаданные, статусы, версии и связи.
- В поиске по knowledge по умолчанию используются только `current` записи. При изменении принципа выполняется `knowledge update`, чтобы не создавать вторую конкурирующую запись.
- Rationale layer хранит проверяемые причины: решения, отклоненные варианты, эксперименты, инварианты и evidence.
- Полные версии rationale-записей лежат в `.project-memory/rationale/**/*.md`; в контекст попадают только короткие выдержки, id, score/reason и путь к полной версии.
- Hybrid search объединяет SQLite FTS5 `bm25()`, vector score, совпадения терминов, path, graph proximity, confidence, layer и recency.
- `./pmem search --debug` показывает компоненты ранжирования.
- `search`, `context`, `impact` и `tests` автоматически запускают локальный `changed` index, если база пустая или stale.
- `status`, `stale`, `audit`, `eval`, `tests --explain` и `watch` помогают проверять качество памяти локально.
- `audit --secrets` ищет возможные секреты в проектных файлах и не печатает найденные значения.
- `optimize` запускает локальное обслуживание SQLite.
- Полные записи открываются только при необходимости.
- У связей есть `confidence`; более точные bindings получают более высокий score.
- Qdrant local + FastEmbed используются для semantic search, если зависимости доступны.
- Если Qdrant/FastEmbed недоступны, включается deterministic fallback, чтобы установка и индексирование не ломались.
- Python parser извлекает modules/classes/functions/methods/imports/calls/inheritance/docstrings.
- JS/TS parser извлекает modules/classes/functions/methods/imports/exports/require/dynamic imports/calls/JSX component references.
- JS/TS parser понимает `tsconfig` aliases, workspace/package aliases и Next.js app routes.
- Для JS/TS используется настраиваемый backend. По умолчанию `auto`: TypeScript compiler API, если в проекте есть `node` и `typescript`; иначе встроенный lexical parser. `tree_sitter` и `lsp` зарезервированы как optional backends без обязательных зависимостей.
- Локальный MCP server предоставляет агентам tools для doctor/status/index/context/impact/search/search_debug/tests/eval/audit/modules/tasks/knowledge/rationale поверх того же `pmem` runtime.
- `tasks check` показывает открытые handoff/user tasks из `.agents/tasks/`, чтобы агент не пропускал задачи от других чатов.
- `tasks close` закрывает task-файл, добавляет completion block и переиндексирует измененную задачу.
- `tasks linear` работает как локальный bridge для Linear: экспортирует `.agents/tasks/` в JSON и импортирует issues обратно в task-файлы.
- `human` module создает Obsidian-like Markdown layer поверх current knowledge/rationale: `.project-memory/human/index.md`, generated notes, `graph.mmd` и `graph.json`.
- `search --layer human` ищет по generated human notes.
- `mcp-config --client claude --write` может записать `.mcp.json`, сохранив существующие настройки.
- Секреты, `.env`, dependency dirs, build outputs, caches и binary files не индексируются.

## Optional Modules

Модули включаются в `.project-memory/config.yaml`.

```yaml
modules:
  human:
    enabled: false
```

`human` выключен по умолчанию. Включение создает `.project-memory/human/`; выключение не удаляет данные.

Human layer нужен, если хочется человекочитаемую Obsidian-like витрину поверх проектной памяти. Он не заменяет `knowledge` и `rationale`; он экспортирует их current-записи в Markdown с frontmatter, backlinks и визуальным graph:

```bash
./pmem modules list
./pmem modules set human --enabled true
./pmem modules set human --enabled false
./pmem human export
./pmem human sync
./pmem human graph
./pmem human search --query "SEO rules"
```

`human sync` подтягивает ручные правки из generated Human notes обратно в `knowledge` или `rationale`. Если Human note и исходная запись изменились после последнего export, команда показывает conflict и не перезаписывает данные молча.

## Linear Sync

Синхронизация задач с Linear

Linear bridge выключен по умолчанию и не требует Linear SDK. `.agents/tasks/` остается локальным источником задач, а `.project-memory/linear/*.json` используется как обменный файл для Linear plugin, MCP или ручной синхронизации.

```bash
./pmem tasks linear status
./pmem tasks linear export --out .project-memory/linear/tasks-export.json
./pmem tasks linear import --file .project-memory/linear/issues.json
```

Импорт создает или обновляет Markdown-задачи в `.agents/tasks/linear/` и переиндексирует их, чтобы другие чаты увидели задачи через `./pmem tasks check`.

## Memory Evals

Локальные evals лежат в `.project-memory/evals/*.jsonl`.

Пример строки:

```json
{"query":"payment validation","expect_path":"src/payments.py"}
```

Запуск:

```bash
./pmem eval --file .project-memory/evals/search.jsonl
```

## Version Updates

Кратко:

- `0.14.0`: Real File Watcher; локальный polling watcher по hash с явным `watch --serve`.
- `0.13.0`: Linear Sync; локальный bridge для экспорта/импорта задач Linear без обязательных зависимостей.
- `0.12.0`: Bidirectional Human Sync; двусторонняя синхронизация Human-слоя с conflict detection.
- `0.11.0`: Human/Obsidian-like layer, `human export/sync/search/graph`, `search --layer human`, MCP human tools, `tasks close`.
- `0.10.0`: npm package smoke, tarball validation, `prepack`, строгий package `files`, проверка Python 3.11+ в Node wrapper, npm distribution guide.
- `0.9.0`: безопасное добавление профилей при upgrade, workspace/package aliases для JS/TS, Next.js route metadata, `.agents/tasks/`, `pmem tasks`, Claude `.mcp.json` writer, secret allowlist/entropy/JWT scan, eval templates, quality guards.
- `0.8.0`: npm/npx distribution, профили `Codex`/`Claude`/`Multi-agent`, Claude Code структура, CI, `audit --secrets`, `optimize`, `mcp-config`.
- `0.7.0`: hybrid search, `search --debug`, `status`, `stale`, `eval`, `audit`, `tests --explain`, `watch --once`, новые MCP tools, parser backend config.
- `0.6.0`: BM25, auto-index, cleanup удаленных файлов, optional `human` module.
- `0.5.0`: локальный MCP server.

Полный список: [CHANGELOG.md](CHANGELOG.md)

## Knowledge Layer

Типы можно задавать свободно. Базовые варианты: `research`, `architecture`, `seo`, `design`, `ux`, `product`, `decision`, `policy`, `note`.

Пример:

```bash
./pmem knowledge add --type seo --title "Product Page SEO" --file docs/seo/product-page.md --tags seo,content
./pmem knowledge context --task "update product page copy"
```

`knowledge context` возвращает короткий список актуальных записей и путь к full markdown. Полную запись открывают только если она действительно нужна для решения.

Если правило изменилось:

```bash
./pmem knowledge update --id product-page-seo --file docs/seo/product-page.md
```

Устаревшее:

```bash
./pmem knowledge retire --id old-product-page-seo
```

## Rationale Layer

Слой rationale помогает не повторять старые тупики. В нем фиксируются выбранные решения, отклоненные варианты, причины ошибок, эксперименты и проектные инварианты. Запись должна опираться на факты: тест, лог, diff, файл, failure или commit.

Пример:

```bash
./pmem rationale add --type decision --title "Use SQLite as Source of Truth" --file docs/rationale/sqlite.md --why "local-first and upgrade-safe" --rejected "Postgres: unnecessary server dependency" --evidence "tests: upgrade preserves graph.sqlite"
./pmem rationale context --task "replace local database"
```

Если причина изменилась:

```bash
./pmem rationale update --id use-sqlite-as-source-of-truth --file docs/rationale/sqlite.md
```

Устаревшее:

```bash
./pmem rationale retire --id old-storage-rationale
```

## Vector Backend

Настройка лежит в `.project-memory/config.yaml`:

```yaml
vector:
  backend: auto
  collection: project_memory_chunks
  embedding_model: null
```

Режимы:

- `auto`: использовать Qdrant/FastEmbed, если они доступны; иначе fallback.
- `qdrant`: требовать Qdrant/FastEmbed и падать при их отсутствии.
- `fallback`: не использовать Qdrant/FastEmbed.

Для semantic search установите зависимости в Python, который запускает `./pmem`:

```bash
python3 -m pip install qdrant-client fastembed
./pmem doctor
./pmem index --mode full
```

Или установите управляемый runtime:

```bash
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target . --with-vector
./pmem doctor
```

Если нужен другой Python:

```bash
PYTHON=/path/to/python ./pmem doctor
PYTHON=/path/to/python ./pmem index --mode full
```

## Разработка

Проверка этого репозитория:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests
```
