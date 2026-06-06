# project-memory-kit

English version: [README.en.md](README.en.md)

`project-memory-kit` добавляет в репозиторий локальную память для агентов, которые пишут код.

Память хранится внутри проекта, поэтому несколько чатов могут работать над одним кодом без потери контекста: агент видит файлы, символы, импорты, обратные зависимости, релевантные тесты, прошлые падения и смысловые правила проекта.

## Что появится в проекте

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
.project-memory/install.json
.project-memory/knowledge/
.project-memory/rationale/
tools/project_memory/
pmem
pmem.ps1
.gitignore
```

Если `AGENTS.md` уже есть, installer сохраняет пользовательский текст и обновляет только managed-блок:

```text
<!-- PMEM:BEGIN -->
...
<!-- PMEM:END -->
```

Внешние skills не управляются этим проектом. Их можно ставить отдельно и описывать правила их использования в `AGENTS.md`.

## Установка

В корне проекта:

```bash
pipx run --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
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
pipx run --no-cache --spec git+https://github.com/AnKu304/project-memory-kit.git pmem upgrade --target .
```

Upgrade обновляет managed-файлы и запускает migrations. Базы и runtime state в `.project-memory/` сохраняются.

## Рабочий цикл агента

Перед правками:

```bash
./pmem doctor
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
pmem install --target .
pmem upgrade --target .
pmem upgrade --target . --with-vector
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
pmem version
```

В установленном проекте:

```bash
./pmem version
./pmem doctor
./pmem migrate
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "описание задачи"
./pmem knowledge add --type research --title "Resource mechanics" --file notes/research.md
./pmem knowledge update --id resource-mechanics --file notes/research.md
./pmem knowledge search --query "SEO rules"
./pmem knowledge context --task "redesign product page"
./pmem knowledge show --id resource-mechanics
./pmem knowledge retire --id old-design-rules
./pmem rationale add --type decision --title "Use SQLite" --file notes/rationale/sqlite.md
./pmem rationale update --id use-sqlite --file notes/rationale/sqlite.md
./pmem rationale search --query "why not postgres"
./pmem rationale context --task "change memory database"
./pmem rationale show --id use-sqlite
./pmem rationale retire --id old-storage-choice
./pmem tests --base HEAD
./pmem search --query "payment validation" --limit 10
./pmem search --query "pricing SEO" --layer knowledge
./pmem search --query "why sqlite" --layer rationale
./pmem record-failure --command "npm test" --log-file ".project-memory/logs/test.log"
./pmem mcp --root .
```

## Локальный MCP

`./pmem mcp` запускает локальный stdio MCP server поверх того же runtime и той же базы `.project-memory/`. Он не создает отдельную память и не отправляет данные во внешний сервис.

Пример подключения для MCP-клиента:

```toml
[mcp_servers.project_memory]
command = "/absolute/path/to/repo/pmem"
args = ["mcp", "--root", "/absolute/path/to/repo"]
```

Доступные MCP tools:

```text
pmem_doctor
pmem_index
pmem_context
pmem_impact
pmem_tests
pmem_search
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
- Поиск ранжируется локально по FTS/vector candidates, score, source и matched terms. Полные записи открываются только при необходимости.
- У связей есть `confidence`; более точные bindings получают более высокий score.
- SQLite FTS дает базовый поиск по chunks.
- Qdrant local + FastEmbed используются для semantic search, если зависимости доступны.
- Если Qdrant/FastEmbed недоступны, включается deterministic fallback, чтобы установка и индексирование не ломались.
- Python parser извлекает modules/classes/functions/methods/imports/calls/inheritance/docstrings.
- JS/TS parser извлекает modules/classes/functions/methods/imports/exports/require/dynamic imports/calls/JSX component references.
- Для JS/TS используется TypeScript compiler API, если в проекте есть `node` и `typescript`; иначе работает встроенный lexical parser.
- Локальный MCP server предоставляет агентам tools для doctor/index/context/impact/search/tests/knowledge/rationale поверх того же `pmem` runtime.
- Секреты, `.env`, dependency dirs, build outputs, caches и binary files не индексируются.

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
