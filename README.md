# project-memory-kit

English version: [README.en.md](README.en.md)

`project-memory-kit` добавляет в репозиторий локальную память для агентов, которые пишут код.

Память хранится внутри проекта, поэтому несколько чатов могут работать над одним кодом без потери контекста: агент видит файлы, символы, импорты, обратные зависимости, релевантные тесты и прошлые падения.

## Что появится в проекте

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
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

Проверка:

```bash
./pmem doctor
./pmem index --mode full
```

## Рабочий цикл агента

Перед правками:

```bash
./pmem doctor
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

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
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
```

В установленном проекте:

```bash
./pmem doctor
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "описание задачи"
./pmem tests --base HEAD
./pmem search --query "payment validation" --limit 10
./pmem record-failure --command "npm test" --log-file ".project-memory/logs/test.log"
```

## Как работает

- SQLite хранит граф проекта: файлы, символы, chunks, imports, calls, inheritance, failures.
- SQLite FTS дает базовый поиск по chunks.
- Qdrant local + FastEmbed используются для semantic search, если зависимости доступны.
- Если Qdrant/FastEmbed недоступны, включается deterministic fallback, чтобы установка и индексирование не ломались.
- Python parser извлекает modules/classes/functions/methods/imports/calls/inheritance/docstrings.
- JS/TS parser извлекает modules/classes/functions/methods/imports/exports/require/dynamic imports/calls/JSX component references.
- Для JS/TS используется TypeScript compiler API, если в проекте есть `node` и `typescript`; иначе работает встроенный lexical parser.
- Секреты, `.env`, dependency dirs, build outputs, caches и binary files не индексируются.

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

Если нужен другой Python:

```bash
PYTHON=/path/to/python ./pmem doctor
PYTHON=/path/to/python ./pmem index --mode full
```

## Что коммитить

Коммитить:

```text
AGENTS.md
.agents/skills/dependency-graph-rag/
.project-memory/config.yaml
.project-memory/.gitignore
.project-memory/README.md
tools/project_memory/
pmem
pmem.ps1
.gitignore
```

Не коммитить:

```text
.project-memory/graph.sqlite
.project-memory/graph.sqlite-*
.project-memory/qdrant/
.project-memory/runtime/
.project-memory/logs/
.project-memory/reports/
.project-memory/cache/
.project-memory/models/
.project-memory/tmp/
```

## Разработка

Проверка этого репозитория:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:src/project_memory_kit/installer/runtime python3 -m unittest discover -s tests
```
