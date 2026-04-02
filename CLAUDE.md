# ESG Reporting Agent

## Project
LangGraph-based ESG (Environmental, Social, Governance) report generation agent using the `deepagents` library (official LangChain OSS). Frontend TBD.

## Stack
- **Runtime**: Python 3.12+, managed with `uv`
- **Agent framework**: `deepagents` (`create_deep_agent`) — official LangChain project built on LangGraph
- **LLM**: Anthropic Claude (`anthropic:claude-sonnet-4-20250514`)
- **Search**: DuckDuckGo via `langchain-community` (no API key required)
- **Source**: `src/esg_agent/`

## Key files
- `src/esg_agent/graph.py` — agent definition (`create_deep_agent`)
- `src/esg_agent/__main__.py` — entry point

## Commands
```bash
uv run python -m esg_agent          # run agent
uv run pytest                       # run tests
uv add <package>                    # add dependency
```

## Environment
Copy `.env.example` to `.env` and set:
- `ANTHROPIC_API_KEY`

## Architecture
Uses `create_deep_agent()` which provides:
- Built-in planning (`write_todos`)
- Built-in filesystem tools (`read_file`, `write_file`, `ls`, `grep`)
- Sub-agent delegation via `task` tool
- State: `messages`, `todos`, `files`, `remaining_steps`

## Conventions
- Agent graph defined in `src/esg_agent/graph.py`
- Add custom tools as plain callables or `BaseTool` subclasses
- Use `context_schema` parameter for custom state fields
