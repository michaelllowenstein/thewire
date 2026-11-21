# TheWire architecture

## Boundaries

- `thewire/__main__.py`: CLI presentation and argument parsing.
- `thewire/core.py`: local domain operations, SQLite schema, plugin manifest registry, subprocess adapter.
- `api/main.py`: loopback read-only FastAPI projections.
- `web/src`: React + TypeScript read-only operator dashboard.
- `plugins/`: sample manifest files; registered copies live under `$THEWIRE_HOME/plugins`.
- `scripts/`: optional shell integration; does not modify existing dotfiles.
- `tests/`: deterministic core tests.

## Data model

`projects(id,name,client,created)`; `sessions(id,project,task,start,end,notes)`; `worklogs(id,project,kind,body,created)`; `executions(id,tool,command,exit_code,created)`.

All timestamps are ISO 8601 UTC. An SQLite partial unique index prevents two active timers. Future migrations should replace automatic schema initialization with a versioned migration framework.

## Planned production design

API -> application services -> repository interfaces -> PostgreSQL. A worker queue processes executions and integrations. Event outbox supports audit and sync. Scoped credentials belong in OS keychain or managed secrets service, never plain manifest JSON. Multi-client separation must be enforced at database query and authorization layers. Build a trusted command allowlist and explicit approval for destructive operations. Add tests for authorization, migrations, crash recovery, time zone boundaries, and exports.

## Plugin contract v0.1

Manifest: `name` (identifier), `executable` (PATH binary), optional `description`, `fixed_args` (array), `timeout_seconds` (integer). CLI arguments are passed without shell expansion. There is no plugin lifecycle API or signed plugin marketplace in this release.

## Proposed events v0.2+

`project.created`, `session.started`, `session.stopped`, `worklog.created`, `tool.executed`, `artifact.attached`, `release.published`. Each event should include event ID, timestamp, actor, project, schema version, and payload.
