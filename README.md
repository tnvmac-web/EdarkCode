# edarkcode

An autonomous coding agent: **research → plan → execute → verify → reflect**.

edarkcode runs in your terminal or your browser, works on a real filesystem with
real tools, remembers what it learned between sessions, and never claims a result
it did not actually observe.

## Status

**v0.1.0 — working foundation.** The agent loop, tools, memory, terminal UI, web
API/UI, and test suite are implemented and pass. This is an honest early release,
not a finished Claude Code competitor. See [Roadmap](#roadmap) for what is and is
not built.

## What works today

| Area | State |
|---|---|
| Agent loop (plan → act → observe → repeat) | ✅ implemented |
| Tools: `read_file`, `write_file`, `edit_file`, `list_dir`, `search`, `run_shell` | ✅ implemented, sandboxed |
| Providers: OpenAI, Anthropic, OpenRouter, Groq, DeepSeek, Ollama | ✅ implemented |
| Streaming terminal UI (rich) | ✅ implemented |
| Web API + WebSocket streaming + browser UI | ✅ implemented |
| Episodic memory (recall across sessions) | ✅ implemented (lexical) |
| Self-improvement (lesson extraction) | ✅ implemented |
| Tool approval / sandboxing | ✅ implemented |
| Test suite | ✅ implemented (pytest) |
| CI/CD (test, lint, build, publish, e2e) | ✅ implemented |
| Native desktop app | ❌ not built (web UI works in any browser) |
| Embedding-based semantic memory | ❌ not built (lexical recall only) |
| Multi-agent orchestration | ❌ not built |

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Configure

```bash
export EDARKCODE_LLM__PROVIDER=openai
export EDARKCODE_LLM__MODEL=gpt-4o-mini
export EDARKCODE_LLM__API_KEY=sk-...
```

Or persist it:

```bash
edarkcode config init
edarkcode config set llm.provider anthropic
edarkcode config set llm.model claude-3-5-sonnet-20241022
edarkcode config set llm.api_key sk-ant-...
edarkcode doctor          # verify the environment
```

Local models need no key:

```bash
export EDARKCODE_LLM__PROVIDER=ollama
export EDARKCODE_LLM__MODEL=qwen2.5-coder:7b
```

## Use

One-shot:

```bash
edarkcode run "add a --json flag to the CLI and update the tests"
```

Interactive:

```bash
edarkcode chat
```

Web UI:

```bash
edarkcode serve --port 8765
# open http://127.0.0.1:8765
```

Memory:

```bash
edarkcode memory list
edarkcode memory lessons
```

Tool calls are approved interactively by default. `--yes` auto-approves;
`edarkcode run "..." --no-show-output` hides tool output.

## Safety

- Every filesystem tool is confined to the workspace root; paths that escape it
  are rejected.
- `run_shell` refuses a small set of destructive patterns and enforces a timeout.
- The agent runs with your privileges — review tool calls before approving, and
  prefer running it in a container or VM on unfamiliar repositories.

## Architecture

```
edarkcode/
  core/
    agent.py      # the loop: plan → execute → reflect, emits StreamEvents
    llm.py        # provider abstraction (OpenAI-compatible + Anthropic), streaming
    factory.py    # wires settings → tools + memory + agent
    prompts.py    # system, planner and reflector prompts
    config.py     # pydantic-settings configuration
    types.py      # Message, ToolResult, StreamEvent, ...
  tools/
    files.py      # sandboxed filesystem tools
    shell.py      # sandboxed shell tool
  memory/
    store.py      # JSONL-backed MemoryStore + LessonStore
  self_improvement/
    reflection.py # distils a finished task into a reusable lesson
  ui/
    terminal.py   # rich renderer for StreamEvents
  web/
    app.py        # FastAPI: /api/run, /api/health, /api/memory, /ws
    static/       # single-file browser UI
```

Everything the agent does is a `StreamEvent`, so the terminal UI, the web UI and
any future front-end render the same stream.

## Test

```bash
pytest
ruff check .
```

Tests use a scripted fake LLM, so the full agent loop is exercised without any
network access or API key.

## Roadmap

- Embedding-based semantic memory (the store interface already supports it).
- Native desktop shell (Tauri) wrapping the existing web UI.
- Multi-agent delegation for large tasks.
- Tree-sitter based repo indexing for better context selection.
- Checkpointing and resumable runs.

## License

MIT.
