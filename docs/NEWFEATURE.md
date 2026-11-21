# Feature implementation runbook

1. Define command name, inputs, outputs, error cases, and side effects.
2. Choose adapter for existing executables or native domain service for shared persistent features.
3. For an adapter, add and register a JSON manifest. Do not use `shell=True` or construct command strings.
4. For a native feature, add service functions to a dedicated module, with explicit storage interface and transaction boundaries.
5. Add a `tw <feature>` parser branch, CLI integration tests, and user documentation.
6. Add API read projections. Before adding write routes, implement authentication, authorization, CSRF strategy where applicable, and audit logging.
7. Add dashboard components using typed API contracts; include loading, empty, and error states.
8. Define database migration, rollback, and backup process for schema changes.
9. Run `pytest -q`, `npm run build`, manual CLI smoke tests, and security review.
10. Publish a versioned release with changelog, SHA-256 checksums, and rollback instructions.

Example feature: `tw docs render --project foo` should use a pure Markdown rendering service, never interpret Markdown as a shell command, and require explicit output path before overwriting files.
