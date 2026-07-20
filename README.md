# Sarvesh's Harness Helper (`@sarveshkhetan/shh`)

A public library of reusable agent skills, subagents, commands, and rules. Install everything with one command via npm — no clone required.

## Install

The repo ships its own installer (`scripts/install.cjs`, exposed as the `shh` bin) that symlinks [`agents/`](./agents/), [`commands/`](./commands/), [`rules/`](./rules/), and optionally [`skills/`](./skills/), hooks, and mcp config into each supported agent harness's global config directory so there is a single source of truth — edit the repo and every linked harness sees the change instantly. Install is **always global and always symlink-based**.

Because it symlinks rather than copies, the package must live at a **stable path**. There are two stable install methods:

### From npm (no clone required) — for end users

**New install:**

```bash
npm install -g @sarveshkhetan/shh        # stable global install
shh --target all --with skills -y      # all harnesses: agents+commands+rules+skills → ~/.claude/, ~/.cursor/, ~/.codex/, ~/.pi/agent/
```

Or install to a single target:

```bash
shh                                    # claude only: agents+commands+rules → ~/.claude/
shh --target cursor --with skills -y   # cursor: agents+rules+skills → ~/.cursor/
```

> **pi agents prerequisite:** pi has no native subagent support. Install the [`pi-sub-agent`](https://pi.dev/packages/pi-sub-agent) extension first (`pi install npm:pi-sub-agent`), then `shh --target pi` will generate and symlink pi-native agent files automatically (see [pi agents](#pi-agents) below).

**Update to a new version:**

```bash
npm update -g @sarveshkhetan/shh        # replaces package contents at the global path
shh --target all --with skills -y      # regenerates pi agents + creates any new symlinks
```

`npm update` replaces the package files in place — existing symlinks for claude/cursor/codex automatically see the new content. Re-running `shh` is needed to regenerate pi agent files (the `.generated/` dir is wiped by `npm update`) and to create symlinks for any newly-added agents/commands/rules/skills. No `--force` needed unless you have conflicting files at the destinations.

**Uninstall:**

```bash
npm uninstall -g @sarveshkhetan/shh     # removes the global package (symlinks will dangle; remove them manually)
```

> **Don't use `npx @sarveshkhetan/shh`.** npx downloads to an ephemeral cache that gets cleaned periodically; symlinks pointing there will dangle. The installer detects this and refuses unless you pass `--i-understand-the-cache-is-ephemeral`. Use `npm install -g` for a stable install.

### From a clone — for you (the author) or contributors

```bash
git clone https://github.com/khetansarvesh/sarvesh-harness-helper
cd sarvesh-harness-helper
npm run install                         # claude: agents+commands+rules → ~/.claude/
```

Update later with `git pull` then `npm run install` (or `shh --target all --with skills -y`). The repo is the canonical source; every linked harness reads from it directly.

### Targets

| Target | `--target` | Global path | Components supported |
| --- | --- | --- | --- |
| Claude Code | `claude` (default) | `~/.claude/` | agents, commands, rules, skills, hooks, mcp, uclaude |
| Cursor | `cursor` | `~/.cursor/` | agents, rules, skills, mcp |
| Codex | `codex` | `~/.codex/` | rules, skills, uclaude |
| pi | `pi` | `~/.pi/agent/` | skills, agents¹, uclaude |

Install to one target, several targets (`a,b`), or all of them:

```bash
node scripts/install.cjs --target cursor --with skills
node scripts/install.cjs --target cursor,codex --with skills -y
node scripts/install.cjs --target all --with skills -y
```

Components a target doesn't support are skipped with a note (e.g. `commands` on cursor, `agents` on codex).

### pi agents

pi has no native subagent support. The [`pi-sub-agent`](https://pi.dev/packages/pi-sub-agent) extension (`pi install npm:pi-sub-agent`) reads `~/.pi/agent/agents/*.md` — but Claude Code agent frontmatter is incompatible with pi:

- Tool names are Capitalized (`Read`, `Grep`, `Glob`, `Bash`) and pi expects lowercase (`read`, `grep`, `find`, `bash`)
- `model` uses Claude aliases (`opus`/`sonnet`/`haiku`) that pi can't resolve
- `color`, `permissionMode`, `mcpServers` are Claude-specific fields

`shh` handles this automatically: when installing to the `pi` target, it generates pi-native agent files at install time — translating tool names (`Read`→`read`, `Glob`→`find`), dropping incompatible fields (`model`/`color`/`permissionMode`/`mcpServers`) — and symlinks those generated files into `~/.pi/agent/agents/`. No separate command needed; it happens as part of the standard `shh --target pi` or `shh --target all` flow.

### Options

| Flag | Description |
| --- | --- |
| `--target <name>` | Target harness: `claude`, `cursor`, `codex`, `pi`, `a,b` list, or `all` (default: `claude`) |
| `--with skills,hooks,mcp` | Additionally include opt-in components |
| `--without rules` | Exclude a default component |
| `--force` | Overwrite existing files/links at the destination |
| `-y, --yes` | Skip the confirmation prompt |

### What gets installed

- `agents/`  → `<target>/agents/`  (default on; claude, cursor, pi¹)
- `commands/` → `<target>/commands/` (default on; claude only)
- `rules/`   → `<target>/rules/`   (default on; claude, cursor, codex; preserves language subdirs)
- `skills/`  → `<target>/skills/`  (`--with skills`; each `SKILL.md` dir linked; all targets)
- `hooks.json` → `~/.claude/hooks.json` (`--with hooks`; claude only)
- `mcp-servers.json` → `~/.claude/mcp-servers.json` (claude) / `~/.cursor/mcp.json` (cursor) (`--with mcp`)
- `user-CLAUDE_AGENT.md` → `~/.claude/CLAUDE.md` (claude) / `~/.codex/AGENTS.md` (codex) / `~/.pi/agent/AGENTS.md` (pi) (default on; renamed to each harness's native user-memory filename; cursor has no on-disk global user-memory file, so skipped there)

¹ pi agents are auto-generated from `agents/*.md` with pi-native frontmatter (see [pi agents](#pi-agents)).

> **Adding a new harness:** add an entry to the `TARGETS` registry in `scripts/install.cjs` with its root path and supported component map.

### Compatibility

- **Portable skills:** directories under [`skills/`](./skills/) containing `SKILL.md`; these are the supported public installation surface.
- **Claude Code integrations:** [`agents/`](./agents/), [`commands/`](./commands/), [`rules/`](./rules/), [`hooks.json`](./hooks.json), and [`mcp-servers.json`](./mcp-servers.json) are installed by the repo's own installer (`npm install -g @sarveshkhetan/shh` + `shh`, or `npm run install` from a clone), which symlinks them into the target harness's global config directory.
- **Executable tools:** a future skill that wraps its own command-line tool may follow the separate AXI pattern—publish an npm package and have its skill invoke `npx -y <package>`. This repository's markdown workflow skills do not require a custom npm installer.

## Contributing skills

Each public skill must live at `skills/<kebab-case-name>/SKILL.md` and begin with YAML frontmatter containing a matching `name` and a non-empty `description`.

```yaml
---
name: example-skill
description: Explain what the skill does and when an agent should use it.
---
```

Before opening a pull request, run:

```bash
npm run verify:skills
```

## 📦 What's Inside

This repo is a **Claude Code plugin** - install it directly or copy components manually.

```
everything-claude-code/
|-- .claude-plugin/   # Plugin and marketplace manifests
|   |-- plugin.json         # Plugin metadata and component paths
|   |-- marketplace.json    # Marketplace catalog for /plugin marketplace add
|
|-- agents/           # Specialized subagents for delegation
|   |-- planner.md           # Feature implementation planning `/plan`
|   |-- architect.md         # System design decisions `/plan` + architect agent
|   |-- tdd-guide.md         # Write Code with tests first `/tdd`
|   |-- code-reviewer.md     # Code Quality and security review `/code-review`
|   |-- security-reviewer.md # Find security vulnerabilities `/security-scan`
|   |-- build-error-resolver.md # fix a failing bug `/build-fix`
|   |-- e2e-runner.md        # Run end to end testing `/e2e`
|   |-- refactor-cleaner.md  # Remove Dead code `/refactor-clean`
|   |-- doc-updater.md       # Update Documentation `/update-docs`
|   |-- go-reviewer.md       # Go code review `/go-review`
|   |-- go-build-resolver.md # Go build error resolution
|   |-- python-reviewer.md   # Python code review `/python-review`
|   |-- database-reviewer.md # Database/Supabase queries review
|
|-- skills/           # Workflow definitions and domain knowledge
|   |-- coding-standards/           # Language best practices
|   |-- clickhouse-io/              # ClickHouse analytics, queries, data engineering
|   |-- backend-patterns/           # API, database, caching patterns
|   |-- frontend-patterns/          # React, Next.js patterns
|   |-- frontend-slides/            # HTML slide decks and PPTX-to-web presentation workflows (NEW)
|   |-- article-writing/            # Long-form writing in a supplied voice without generic AI tone (NEW)
|   |-- content-engine/             # Multi-platform social content and repurposing workflows (NEW)
|   |-- market-research/            # Source-attributed market, competitor, and investor research (NEW)
|   |-- investor-materials/         # Pitch decks, one-pagers, memos, and financial models (NEW)
|   |-- investor-outreach/          # Personalized fundraising outreach and follow-up (NEW)
|   |-- continuous-learning/        # Auto-extract patterns from sessions (Longform Guide)
|   |-- continuous-learning-v2/     # Instinct-based learning with confidence scoring
|   |-- iterative-retrieval/        # Progressive context refinement for subagents
|   |-- strategic-compact/          # Manual compaction suggestions (Longform Guide)
|   |-- tdd-workflow/               # TDD methodology
|   |-- security-review/            # Security checklist
|   |-- eval-harness/               # Verification loop evaluation (Longform Guide)
|   |-- verification-loop/          # Continuous verification (Longform Guide)
|   |-- videodb/                   # Video and audio: ingest, search, edit, generate, stream (NEW)
|   |-- golang-patterns/            # Go idioms and best practices
|   |-- golang-testing/             # Go testing patterns, TDD, benchmarks
|   |-- cpp-coding-standards/         # C++ coding standards from C++ Core Guidelines (NEW)
|   |-- cpp-testing/                # C++ testing with GoogleTest, CMake/CTest (NEW)
|   |-- django-patterns/            # Django patterns, models, views (NEW)
|   |-- django-security/            # Django security best practices (NEW)
|   |-- django-tdd/                 # Django TDD workflow (NEW)
|   |-- django-verification/        # Django verification loops (NEW)
|   |-- python-patterns/            # Python idioms and best practices (NEW)
|   |-- python-testing/             # Python testing with pytest (NEW)
|   |-- springboot-patterns/        # Java Spring Boot patterns (NEW)
|   |-- springboot-security/        # Spring Boot security (NEW)
|   |-- springboot-tdd/             # Spring Boot TDD (NEW)
|   |-- springboot-verification/    # Spring Boot verification (NEW)
|   |-- configure-ecc/              # Interactive installation wizard (NEW)
|   |-- security-scan/              # AgentShield security auditor integration (NEW)
|   |-- java-coding-standards/     # Java coding standards (NEW)
|   |-- jpa-patterns/              # JPA/Hibernate patterns (NEW)
|   |-- postgres-patterns/         # PostgreSQL optimization patterns (NEW)
|   |-- nutrient-document-processing/ # Document processing with Nutrient API (NEW)
|   |-- project-guidelines-example/   # Template for project-specific skills
|   |-- database-migrations/         # Migration patterns (Prisma, Drizzle, Django, Go) (NEW)
|   |-- api-design/                  # REST API design, pagination, error responses (NEW)
|   |-- deployment-patterns/         # CI/CD, Docker, health checks, rollbacks (NEW)
|   |-- docker-patterns/            # Docker Compose, networking, volumes, container security (NEW)
|   |-- e2e-testing/                 # Playwright E2E patterns and Page Object Model (NEW)
|   |-- content-hash-cache-pattern/  # SHA-256 content hash caching for file processing (NEW)
|   |-- cost-aware-llm-pipeline/     # LLM cost optimization, model routing, budget tracking (NEW)
|   |-- regex-vs-llm-structured-text/ # Decision framework: regex vs LLM for text parsing (NEW)
|   |-- swift-actor-persistence/     # Thread-safe Swift data persistence with actors (NEW)
|   |-- swift-protocol-di-testing/   # Protocol-based DI for testable Swift code (NEW)
|   |-- search-first/               # Research-before-coding workflow (NEW)
|   |-- skill-stocktake/            # Audit skills and commands for quality (NEW)
|   |-- liquid-glass-design/         # iOS 26 Liquid Glass design system (NEW)
|   |-- foundation-models-on-device/ # Apple on-device LLM with FoundationModels (NEW)
|   |-- swift-concurrency-6-2/       # Swift 6.2 Approachable Concurrency (NEW)
|   |-- perl-patterns/             # Modern Perl 5.36+ idioms and best practices (NEW)
|   |-- perl-security/             # Perl security patterns, taint mode, safe I/O (NEW)
|   |-- perl-testing/              # Perl TDD with Test2::V0, prove, Devel::Cover (NEW)
|   |-- autonomous-loops/           # Autonomous loop patterns: sequential pipelines, PR loops, DAG orchestration (NEW)
|   |-- plankton-code-quality/      # Write-time code quality enforcement with Plankton hooks (NEW)
|
|-- commands/         # Slash commands for quick execution
|   |-- tdd.md              # /tdd - Test-driven development
|   |-- plan.md             # /plan - Implementation planning
|   |-- e2e.md              # /e2e - E2E test generation
|   |-- code-review.md      # /code-review - Quality review
|   |-- build-fix.md        # /build-fix - Fix build errors
|   |-- refactor-clean.md   # /refactor-clean - Dead code removal
|   |-- learn.md            # /learn - Extract patterns mid-session (Longform Guide)
|   |-- learn-eval.md       # /learn-eval - Extract, evaluate, and save patterns (NEW)
|   |-- checkpoint.md       # /checkpoint - Save verification state (Longform Guide)
|   |-- verify.md           # /verify - Run verification loop (Longform Guide)
|   |-- setup-pm.md         # /setup-pm - Configure package manager
|   |-- go-review.md        # /go-review - Go code review (NEW)
|   |-- go-test.md          # /go-test - Go TDD workflow (NEW)
|   |-- go-build.md         # /go-build - Fix Go build errors (NEW)
|   |-- skill-create.md     # /skill-create - Generate skills from git history (NEW)
|   |-- instinct-status.md  # /instinct-status - View learned instincts (NEW)
|   |-- instinct-import.md  # /instinct-import - Import instincts (NEW)
|   |-- instinct-export.md  # /instinct-export - Export instincts (NEW)
|   |-- evolve.md           # /evolve - Cluster instincts into skills
|   |-- pm2.md              # /pm2 - PM2 service lifecycle management (NEW)
|   |-- multi-plan.md       # /multi-plan - Multi-agent task decomposition (NEW)
|   |-- multi-execute.md    # /multi-execute - Orchestrated multi-agent workflows (NEW)
|   |-- multi-backend.md    # /multi-backend - Backend multi-service orchestration (NEW)
|   |-- multi-frontend.md   # /multi-frontend - Frontend multi-service orchestration (NEW)
|   |-- multi-workflow.md   # /multi-workflow - General multi-service workflows (NEW)
|   |-- orchestrate.md      # /orchestrate - Multi-agent coordination
|   |-- sessions.md         # /sessions - Session history management
|   |-- eval.md             # /eval - Evaluate against criteria
|   |-- test-coverage.md    # /test-coverage - Test coverage analysis
|   |-- update-docs.md      # /update-docs - Update documentation
|   |-- update-codemaps.md  # /update-codemaps - Update codemaps
|   |-- python-review.md    # /python-review - Python code review (NEW)
|
|-- rules/            # Always-follow guidelines (copy to ~/.claude/rules/)
|   |-- README.md            # Structure overview and installation guide
|   |-- common/              # Language-agnostic principles
|   |   |-- coding-style.md    # Immutability, file organization
|   |   |-- git-workflow.md    # Commit format, PR process
|   |   |-- testing.md         # TDD, 80% coverage requirement
|   |   |-- performance.md     # Model selection, context management
|   |   |-- patterns.md        # Design patterns, skeleton projects
|   |   |-- hooks.md           # Hook architecture, TodoWrite
|   |   |-- agents.md          # When to delegate to subagents
|   |   |-- security.md        # Mandatory security checks
|   |-- typescript/          # TypeScript/JavaScript specific
|   |-- python/              # Python specific
|   |-- golang/              # Go specific
|   |-- swift/               # Swift specific
|   |-- php/                 # PHP specific (NEW)
|
|-- hooks/            # Trigger-based automations
|   |-- README.md                 # Hook documentation, recipes, and customization guide
|   |-- hooks.json                # All hooks config (PreToolUse, PostToolUse, Stop, etc.)
|   |-- memory-persistence/       # Session lifecycle hooks (Longform Guide)
|   |-- strategic-compact/        # Compaction suggestions (Longform Guide)
|
|-- scripts/          # Cross-platform Node.js scripts (NEW)
|   |-- lib/                     # Shared utilities
|   |   |-- utils.js             # Cross-platform file/path/system utilities
|   |   |-- package-manager.js   # Package manager detection and selection
|   |-- hooks/                   # Hook implementations
|   |   |-- session-start.js     # Load context on session start
|   |   |-- session-end.js       # Save state on session end
|   |   |-- pre-compact.js       # Pre-compaction state saving
|   |   |-- suggest-compact.js   # Strategic compaction suggestions
|   |   |-- evaluate-session.js  # Extract patterns from sessions
|   |-- setup-package-manager.js # Interactive PM setup
|
|-- examples/         # Example configurations and sessions
|   |-- CLAUDE.md             # Example project-level config
|   |-- user-CLAUDE.md        # Example user-level config
|   |-- saas-nextjs-CLAUDE.md   # Real-world SaaS (Next.js + Supabase + Stripe)
|   |-- go-microservice-CLAUDE.md # Real-world Go microservice (gRPC + PostgreSQL)
|   |-- django-api-CLAUDE.md      # Real-world Django REST API (DRF + Celery)
|   |-- rust-api-CLAUDE.md        # Real-world Rust API (Axum + SQLx + PostgreSQL) (NEW)
|
|-- mcp-servers.json    # GitHub, Supabase, Vercel, Railway, etc.
```

## 📥 Manual Installation

```bash
# Copy agents to your Claude config
cp /agents/*.md ~/.claude/agents/

# Copy rules (common + language-specific)
cp -r /rules/common/* ~/.claude/rules/
cp -r /rules/typescript/* ~/.claude/rules/   # pick your stack
cp -r /rules/python/* ~/.claude/rules/
cp -r /rules/golang/* ~/.claude/rules/
cp -r /rules/php/* ~/.claude/rules/

# Copy commands
cp /commands/*.md ~/.claude/commands/

# Copy skills

# Copy Hooks
Copy the hooks from `hooks.json` to your `~/.claude/settings.json`.

# Configure MCPs
Copy desired MCP servers from `/mcp-servers.json` to your `~/.claude.json`.
```

**Important:** Replace `YOUR_*_HERE` placeholders with your actual API keys.

## Common Workflows

**Starting a new feature:**

```
/plan → planner creates implementation blueprint
/tdd → tdd-guide enforces write-tests-first
/code-review
```

**Fixing a bug:**

```
/tdd → tdd-guide: write a failing test that reproduces it
/plan → implement the fix, verify test passes
/code-review
```

**Preparing for production:**

```
/security-scan → security-reviewer
/e2e → e2e-runner: critical user flow tests
/test-coverage → verify 80%+ coverage
```

---

## Note on Tools and MCPs

My context window is shrinking / Claude is running out of context

- Cause : Too many MCP servers eat your context. Each MCP tool description consumes tokens from your 200k window, potentially reducing it to ~70k.
- Fix: Disable unused MCPs per project:

```json
// In your project's .claude/settings.json
{
  "disabledMcpServers": ["supabase", "railway", "vercel"]
}
```

Keep under 10 MCPs enabled and under 80 tools active.

## 🔗 Links

- **Shorthand Guide (Start Here):** [The Shorthand Guide to Everything Claude Code](https://x.com/affaanmustafa/status/2012378465664745795)
- **Longform Guide (Advanced):** [The Longform Guide to Everything Claude Code](https://x.com/affaanmustafa/status/2014040193557471352)
- **Skills Directory:** awesome-agent-skills (community-maintained directory of agent skills)
