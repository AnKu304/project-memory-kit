# project-memory-kit

`project-memory-kit` устанавливает локальную проектную память для coding agents в любой новый или уже существующий репозиторий.

Идея простая: если один проект ведется в нескольких чатах под разные задачи, агент не должен каждый раз начинать с нуля и править файлы без учета зависимостей. В проект добавляется общий локальный слой памяти: граф файлов/символов/импортов, поиск по chunks, impact analysis, контекст изменений, выбор тестов и память о падениях.

## Что Это Решает

Обычная проблема агента:

```text
прочитал задачу -> открыл очевидный файл -> поправил -> не учел зависимости
```

Желаемый процесс:

```text
прочитал задачу
-> обновил локальную память проекта
-> нашел затронутые файлы и символы
-> увидел reverse imports/callers/tests/старые failures
-> собрал CHANGE_CONTEXT.md
-> сделал минимальную правку
-> пересчитал impact
-> запустил целевые тесты
-> записал failure memory, если тест упал
-> отчитался о рисках
```

Такой процесс особенно полезен, когда один и тот же проект открывается в нескольких Codex/ChatGPT чатах: память лежит в проекте, а не в конкретном диалоге.

## Финальный Стек

- Graph memory: SQLite property graph.
- Vector boundary: Qdrant local mode path with deterministic offline vector fallback.
- Embeddings: FastEmbed-compatible architecture, deterministic fallback for tests/offline bootstrap.
- Parser: Python `ast` + `symtable`.
- CLI: `pmem`.
- Agent protocol: `AGENTS.md` managed block.
- Agent skill: `.agents/skills/dependency-graph-rag/`.

## Важное Разделение

`project-memory-kit` устанавливает только:

```text
.project-memory/
tools/project_memory/
.agents/skills/dependency-graph-rag/
AGENTS.md managed block
pmem
pmem.ps1
```

Сторонние skills для дизайна, frontend, Next.js, документов и других задач ставятся отдельно обычным способом, например:

```bash
npx skills add https://github.com/anthropics/skills --skill frontend-design
npx skills add https://github.com/vercel-labs/next-skills --skill next-best-practices
```

В `AGENTS.md` есть пользовательская секция, где можно описать, когда применять такие skills в конкретном проекте.

## Соответствие Codex Skills

Skill `dependency-graph-rag` сделан по текущей документации Codex Skills:

- `SKILL.md` содержит обязательные поля `name` и `description`;
- инструкции лежат в самом `SKILL.md`;
- дополнительные материалы лежат в `references/`;
- UI metadata для Codex app лежит в `agents/openai.yaml`;
- описание front-loaded, чтобы Codex мог выбрать skill по implicit invocation даже при сокращении списка skills.

Использованные источники:

- [Using skills in Codex](https://developers.openai.com/codex/skills)
- [Create custom skills in Codex](https://developers.openai.com/codex/skills#create-a-skill)
- [openai/skills](https://github.com/openai/skills)

## Установка В Новый Проект

Один раз создайте и опубликуйте этот репозиторий на GitHub. Потом в любом новом проекте:

```bash
mkdir my-app
cd my-app
git init
pipx run --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

Если нужно гарантированно взять свежий commit из GitHub, добавьте `--no-cache` перед `--spec`.

После установки в проекте появятся:

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

Если `AGENTS.md` отсутствует, installer создает полноценный шаблон-инструкцию, а не только memory-блок. В нем есть места для:

- описания проекта;
- ссылок на `README.md`, `PROJECT_RULES.md`, `TASK.md`, `RULES.md`;
- пользовательских правил кодинга, архитектуры, безопасности и деплоя;
- правил, когда использовать внешние skills;
- managed-блока `project-memory-kit`.

Если `AGENTS.md` уже существует, installer сохраняет весь пользовательский текст и добавляет или обновляет только managed-блок `<!-- PMEM:BEGIN --> ... <!-- PMEM:END -->`.

Проверка:

```bash
./pmem doctor
./pmem index --mode full
./pmem impact --base HEAD --format markdown
./pmem context --task "test task" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

## Установка В Существующий Проект

В корне существующего repo:

```bash
pipx run --spec git+https://github.com/AnKu304/project-memory-kit.git pmem init --target .
```

Installer:

- не создает вложенную папку проекта;
- не перетирает существующий `AGENTS.md`;
- обновляет только блок `<!-- PMEM:BEGIN --> ... <!-- PMEM:END -->`;
- при создании нового `AGENTS.md` добавляет user-editable секции для проектных правил и внешних skills;
- не трогает внешние skills в `.agents/skills/*`;
- устанавливает только `.agents/skills/dependency-graph-rag/`;
- безопасно merge-ит `.gitignore`;
- создает локальный runtime `tools/project_memory/`;
- создает wrappers `./pmem` и `./pmem.ps1`.

## Что Коммитить

Коммитить:

```bash
git add AGENTS.md \
  .agents/skills/dependency-graph-rag \
  .project-memory/config.yaml \
  .project-memory/.gitignore \
  .project-memory/README.md \
  tools/project_memory \
  pmem pmem.ps1 .gitignore
git commit -m "Add local project memory"
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

Эти пути добавляются в managed-блок `.gitignore`.

## Обязательный Workflow Агента

Перед осмысленными правками:

```bash
./pmem doctor
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem context --task "<current task>" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

Агент обязан прочитать:

```text
.project-memory/reports/CHANGE_CONTEXT.md
```

После правок:

```bash
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem tests --base HEAD
```

При падении тестов:

```bash
mkdir -p .project-memory/logs
./pmem record-failure --command "<failed command>" --log-file "<log path>"
./pmem context --task "fix failing tests after current change" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
```

## Команды

Installer-level:

```bash
pmem init --target .
pmem install --target .
pmem upgrade --target .
pmem uninstall --target . --keep-memory
pmem uninstall --target . --purge
```

Installed project runtime:

```bash
./pmem init
./pmem doctor
./pmem index --mode full
./pmem index --mode changed
./pmem impact --base HEAD --format markdown
./pmem impact --base HEAD --format json
./pmem context --task "описание задачи" --base HEAD --out .project-memory/reports/CHANGE_CONTEXT.md
./pmem tests --base HEAD
./pmem record-failure --command "python -m unittest" --log-file ".project-memory/logs/test.log"
./pmem search --query "payment validation" --limit 10
```

## Как Работает Индексация

Индексатор:

- уважает `.project-memory/config.yaml`;
- пропускает `.git`, `.project-memory`, virtualenv, dependency dirs, build dirs, caches;
- не индексирует `.env`, private keys, tokens, credentials, secrets и binary files;
- хеширует файлы и пропускает неизмененные;
- для Python извлекает modules/classes/functions/methods/imports/calls/inheritance/docstrings/line ranges;
- сохраняет nodes/edges/chunks в SQLite;
- пишет FTS chunks;
- пишет local vector records в `.project-memory/qdrant/`.

## Graph Schema

Node kinds:

```text
Project, Directory, File, Module, Symbol, Chunk, Layer, Test, Command, Error, Failure, Fix, ChangeSet, Decision
```

Edge kinds:

```text
CONTAINS, DEFINES, IMPORTS, CALLS, INHERITS, REFERENCES, BELONGS_TO_LAYER, TESTS, COVERS_FILE, DESCRIBES, MENTIONS, TOUCHES, OCCURRED_IN, FIXED_BY, CHANGED, CONSTRAINS
```

Базовые связи:

```text
File -> DEFINES -> Symbol
Chunk -> DESCRIBES -> Symbol
Chunk -> DESCRIBES -> File
Test -> TESTS -> Symbol
Test -> COVERS_FILE -> File
ChangeSet -> TOUCHES -> File/Symbol
Error -> OCCURRED_IN -> File/Symbol/Test
Error -> FIXED_BY -> ChangeSet/Fix
```

## Локальная Проверка Этого Репозитория

```bash
PYTHONPATH=src:src/project_memory_kit/installer/runtime python -m unittest discover -s tests
```

Проверка установки в temp repo покрывает:

- создание boilerplate;
- сохранение существующего `AGENTS.md`;
- замену только managed-блока;
- safe merge `.gitignore`;
- сохранность внешних skills;
- работу `./pmem doctor`;
- работу `./pmem index`;
- генерацию `CHANGE_CONTEXT.md`.

## Ограничения Первой Версии

- Базовая память работает для любых текстовых проектов: индексирует файлы, chunks, поиск, git diff, context reports, тестовые команды и failure memory.
- Глубокий symbol graph в первой версии реализован для Python через `ast` + `symtable`.
- В проектах на JavaScript, TypeScript, Next.js и других стеках память все равно полезна на уровне файлов, текста, контекста изменений и истории ошибок. Для такой же точной карты символов, импортов и вызовов под эти языки нужно добавить отдельный parser backend.
- Vector layer использует deterministic fallback, чтобы bootstrap и tests не требовали скачивания моделей. Для production-поиска можно подключить реальные FastEmbed/Qdrant dependencies глубже.
