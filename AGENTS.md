# Repository Guidance

- Authoritative skill definitions live under `skills/`.
- Codex-discoverable repo skills live under `.agents/skills/`, typically as symlinks back to `skills/`.
- When updating an existing skill, edit the source under `skills/` rather than editing the bridge path.
- Invoke skills explicitly with `$skill-name` when you want to force selection.
- For `job-scan`, run commands from the repository root so relative script paths resolve correctly.
