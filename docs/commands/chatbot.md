# prism chatbot

Start an AI chatbot agent that orchestrates Prism's MCP tools using a
natural-language interface. The agent connects to an OpenAI-compatible
LLM API and exposes all registered Prism MCP tools (SQL, documents,
terminal, testing, etc.) as function-calling capabilities — the LLM
decides which tools to call and in what order.

## How it works

```
User message → LLM API → tool calls? → execute via MCP → results → LLM API → final answer
                     ↑__________________________|
```

1. The agent starts an **in-memory** Prism MCP server (same tools as
   `prism serve`, no HTTP transport needed).
2. It discovers all registered tools and converts their schemas to
   OpenAI function-calling format.
3. It sends the user's message to the LLM API with the tool definitions.
4. If the LLM responds with tool calls, the agent executes them via the
   MCP client and feeds the results back.
5. This loop repeats until the LLM produces a final text response.

## Prerequisites

You need access to an **OpenAI-compatible LLM API**. This includes:

| Provider | API URL |
|----------|---------|
| OpenAI | `https://api.openai.com/v1` |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<deployment>` |
| vLLM | `http://localhost:8000/v1` |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| Any OpenAI-compatible endpoint | `<base-url>/v1` |

## Configuration

### Quick start

```bash
# Save credentials persistently
prism config \
  --chatbot-api-url https://api.openai.com/v1 \
  --chatbot-api-key sk-... \
  --chatbot-model gpt-4o \
  --chatbot-skills-path ./skills

# Start the chatbot (settings are read from config.json)
prism chatbot
```

### Configuration sources (precedence: high → low)

1. **Command-line flags** — `--api-url`, `--api-key`, `--model`, `--skills-path`
2. **Environment variables** — `CHATBOT_API_URL`, `CHATBOT_API_KEY`,
   `CHATBOT_MODEL`, `CHATBOT_SKILLS_PATH`
3. **`config.json`** — written by `prism config --chatbot-api-url …`

!!! tip
    When you pass `--api-url`, `--api-key`, `--model`, or
    `--skills-path` on the command line, they are **automatically saved**
    to `config.json` for future runs. Use `--no-save` to disable this
    behaviour.

## Usage

### Interactive mode (REPL)

```bash
prism chatbot
```

Drops into an interactive prompt where you can type natural-language
requests:

```
Prism 0.2.1-beta2 — Chatbot Agent
  LLM API: https://api.openai.com/v1
  Model:   gpt-4o
  Skills:  ./skills
  Type 'help' for commands, 'exit' to quit.

you> What tables exist in the USER namespace?
  thinking...
  → calling execute_sql({"query": "SELECT SqlTableName FROM %Dictionary.ClassDefinition WHERE ..."})...
  ← execute_sql returned: 245 chars

agent> The USER namespace contains 12 tables...
```

### One-shot mode

Pass a message as an argument to get a single response:

```bash
prism chatbot "What is the IRIS version?"
```

### List loaded skills

```bash
prism chatbot --list-skills
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--api-url` | | OpenAI-compatible API base URL |
| `--api-key` | | API key for the LLM provider |
| `--model` | | Model name (default: `gpt-4o`) |
| `--skills-path` | | Path to a folder of markdown skill files |
| `--save` / `--no-save` | | Persist provided flags to `config.json` (default: save) |
| `--list-skills` | | List skill files in the configured path and exit |

## Skills

Skills are markdown (`.md`) files that are loaded and injected into the
agent's system prompt. They provide the LLM with domain-specific
instructions on how to use the available tools.

### Skill file format

Any `.md` file inside the skills directory is loaded. The file name
becomes the skill name (e.g. `sql/rest-apis.md` → `sql/rest-apis`).

```
skills/
├── sql/
│   ├── rest-apis.md       # How to create REST API classes
│   └── queries.md        # SQL query patterns
├── testing.md             # How to run unit tests
└── debugging.md           # Debug workflow guide
```

### Example skill file

```markdown
# Creating a REST API class

1. Use `put_and_compile` to create a class that extends `%CSP.REST`.
2. Define `UrlMap` XData block with route definitions.
3. Each route maps an HTTP method + URL pattern to a class method.
4. Test the endpoint with `execute_sql` using a `CALL` statement.

Example:
- Class: `MyApp.RESTHandler.cls`
- Route: `GET /users` → `GetUsers` method
```

## Available tools

The chatbot agent has access to all Prism MCP tools registered on the
server. The exact set depends on your configuration:

| Category | Count | Condition |
|----------|-------|-----------|
| Always-on | 11 | SQL, documents, terminal, testing, indexing |
| Workspace-gated | 2 | `IRIS_WORKSPACE` is set (`put_document`, `put_and_compile`) |
| Debug-gated | 9 | `IRIS_DEBUG_ENABLED=true` (`debug_*` tools) |

See the [MCP tool reference](../mcp/tools.md) for the full list.

## Config settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATBOT_API_URL` | *(empty)* | OpenAI-compatible API base URL |
| `CHATBOT_API_KEY` | *(empty)* | API key for the LLM provider |
| `CHATBOT_MODEL` | `gpt-4o` | Model name to use |
| `CHATBOT_SKILLS_PATH` | *(empty)* | Path to a folder of markdown skill files |

## Examples

### Using vLLM (local model)

```bash
prism chatbot \
  --api-url http://localhost:8000/v1 \
  --api-key dummy \
  --model Qwen/Qwen2.5-72B-Instruct
```

### Using Ollama

```bash
prism chatbot \
  --api-url http://localhost:11434/v1 \
  --api-key dummy \
  --model llama3.1
```

### One-shot query

```bash
prism chatbot "List all classes in the MyApp package"
```

### With skills

```bash
mkdir -p skills
echo "# IRIS SQL Guide\nUse execute_sql for all queries." > skills/sql-guide.md
prism chatbot --skills-path ./skills
```
