#!/usr/bin/env node
/**
 * @sarveshkhetan/shh installer — multi-target agent harness installer.
 *
 * Symlinks agents/, commands/, rules/, skills/, hooks, mcp config, and the
 * root-level user-memory file (user-CLAUDE_AGENT.md, renamed per target) from
 * this repository's canonical source directory into each supported agent
 * harness's global config directory. Always global, always symlink-based.
 *
 * Symlinks keep a single source of truth: edit the repo and every linked
 * harness sees the change instantly.
 *
 * Not every harness supports every component — the target adapter declares
 * which components it accepts and where each one lands. Unsupported selected
 * components are skipped with a note.
 *
 * Usage:
 *   node scripts/install.cjs                            # all harnesses, agents+commands+rules+skills
 *   node scripts/install.cjs --target cursor            # cursor only
 *   node scripts/install.cjs --target all               # every supported harness
 *   node scripts/install.cjs --with skills,hooks,mcp
 *   node scripts/install.cjs --without rules
 *   node scripts/install.cjs --force                    # overwrite existing files/links
 *   shh                                                # when published to npm as @sarveshkhetan/shh
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

// ---------------------------------------------------------------------------
// Component registry
// ---------------------------------------------------------------------------

// Source-side description of each component. The destination path is NOT here —
// it lives in the target adapter, because e.g. cursor's mcp file is `mcp.json`
// while claude's is `mcp-servers.json`, and some harnesses don't support some
// components at all.
//
// `walk: true`  → link each leaf file matching `extension` (preserving subdirs)
// `walk: false` → link a single file
// `extension: null` with `walk: true` → link each child *directory* containing
//   SKILL.md (used by skills, which are directory-shaped)
const COMPONENTS = [
  {
    id: 'agents',
    source: 'agents',
    walk: true,
    extension: '.md',
    defaultOn: true,
    description: 'Subagent definitions (.md).',
  },
  {
    id: 'commands',
    source: 'commands',
    walk: true,
    extension: '.md',
    defaultOn: true,
    description: 'Slash command definitions (.md).',
  },
  {
    id: 'rules',
    source: 'rules',
    walk: true,
    extension: '.md',
    defaultOn: true,
    description: 'Language and common rule packs (.md, nested by language).',
  },
  {
    id: 'skills',
    source: 'skills',
    walk: true,
    extension: null,
    defaultOn: true,
    description: 'Portable skills (directories with SKILL.md).',
  },
  {
    id: 'hooks',
    source: 'hooks.json',
    walk: false,
    defaultOn: false,
    description: 'Hook configuration (hooks.json).',
  },
  {
    id: 'mcp',
    source: 'mcp-servers.json',
    walk: false,
    defaultOn: false,
    description: 'MCP server catalog (mcp-servers.json).',
  },
  // Root-level user-memory file. The source filename is Claude-flavored
  // (`user-CLAUDE_AGENT.md`) but each target renames it to that harness's
  // native user-instructions filename (CLAUDE.md / AGENTS.md) via the target
  // adapter's component map — same per-target rename pattern hooks/mcp use.
  // defaultOn because this is core user instructions, parallel to agents/rules.
  {
    id: 'uclaude',
    source: 'user-CLAUDE_AGENT.md',
    walk: false,
    defaultOn: true,
    description: 'User-level agent instructions (user-CLAUDE_AGENT.md → CLAUDE.md / AGENTS.md).',
  },
];

const COMPONENT_BY_ID = new Map(COMPONENTS.map(c => [c.id, c]));

// ---------------------------------------------------------------------------
// Target adapters
// ---------------------------------------------------------------------------

// Each adapter declares:
//   root       → absolute path to the harness's global config directory
//   components → map of componentId → destination subpath (relative to root).
//                Omitting a componentId means "not supported by this harness".
//
// When adding a new harness, add an entry here.
const h = p => path.join(os.homedir(), p);
const TARGETS = {
  claude: {
    root: () => h('.claude'),
    components: {
      agents: 'agents',
      commands: 'commands',
      rules: 'rules',
      skills: 'skills',
      hooks: 'hooks.json',
      mcp: 'mcp-servers.json',
      // Claude Code user memory lives at ~/.claude/CLAUDE.md.
      uclaude: 'CLAUDE.md',
    },
  },
  cursor: {
    root: () => h('.cursor'),
    components: {
      agents: 'agents',
      rules: 'rules',
      skills: 'skills',
      // cursor has no slash-commands and no hooks; its mcp file is mcp.json.
      // cursor also has no on-disk global user-memory file (User Rules live in
      // the app via Customize → Rules), so uclaude is intentionally omitted.
      mcp: 'mcp.json',
    },
  },
  codex: {
    root: () => h('.codex'),
    components: {
      rules: 'rules',
      skills: 'skills',
      // codex has no markdown subagents, no slash commands, no hooks.
      // its mcp config is config.toml (TOML, not JSON) — not linkable here.
      // Codex global user guidance lives at ~/.codex/AGENTS.md.
      uclaude: 'AGENTS.md',
    },
  },
  pi: {
    root: () => h('.pi/agent'),
    components: {
      skills: 'skills',
      // pi has no native subagent support; the `pi-sub-agent` extension (or the
      // built-in subagents in newer pi builds) reads ~/.pi/agent/agents/*.md.
      // Claude agent frontmatter is incompatible (Capitalized tool names, model
      // aliases like `opus`, Claude-only `color`/`permissionMode` fields), so we
      // generate pi-native agent files at install time and symlink those.
      // See `transformAgentForPi` below.
      agents: 'agents',
      // pi loads AGENTS.md (or CLAUDE.md) at startup; ~/.pi/agent/AGENTS.md is
      // the documented global-instructions location.
      uclaude: 'AGENTS.md',
    },
  },
};
const TARGET_IDS = Object.keys(TARGETS);

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = {
    targets: [...TARGET_IDS],
    force: false,
    yes: false,
    help: false,
    acceptEphemeral: false,
    include: new Set(),
    exclude: new Set(),
  };

  const setTargets = (raw) => {
    const list = String(raw || '').split(',').map(s => s.trim()).filter(Boolean);
    if (list.length === 1 && list[0] === 'all') {
      opts.targets = [...TARGET_IDS];
    } else {
      for (const t of list) {
        if (!TARGETS[t]) throw new Error(`Unknown target '${t}'. Supported: ${TARGET_IDS.join(', ')} (or 'all')`);
      }
      opts.targets = list;
    }
  };

  for (let i = 0; i < args.length; i += 1) {
    const a = args[i];
    if (a === '-h' || a === '--help') opts.help = true;
    else if (a === '--i-understand-the-cache-is-ephemeral') opts.acceptEphemeral = true;
    else if (a === '--force') opts.force = true;
    else if (a === '-y' || a === '--yes') opts.yes = true;
    else if (a === '--target') setTargets(args[++i]);
    else if (a.startsWith('--target=')) setTargets(a.slice(9));
    else if (a === '--with') String(args[++i] || '').split(',').map(s => s.trim()).filter(Boolean).forEach(s => opts.include.add(s));
    else if (a === '--without') String(args[++i] || '').split(',').map(s => s.trim()).filter(Boolean).forEach(s => opts.exclude.add(s));
    else if (a.startsWith('--with=')) a.slice(7).split(',').forEach(s => opts.include.add(s.trim()));
    else if (a.startsWith('--without=')) a.slice(10).split(',').forEach(s => opts.exclude.add(s.trim()));
    else { throw new Error(`Unknown argument: ${a} (see --help)`); }
  }

  // Validate --with / --against component ids
  for (const id of [...opts.include, ...opts.exclude]) {
    if (!COMPONENT_BY_ID.has(id)) throw new Error(`Unknown component '${id}'. Supported: ${COMPONENTS.map(c => c.id).join(', ')}`);
  }
  return opts;
}

function helpText() {
  const compList = COMPONENTS.map(c => `  ${c.id.padEnd(8)} ${c.defaultOn ? '[default on] ' : '[opt-in]    '}${c.description}`).join('\n');
  const tgtList = TARGET_IDS.map(t => {
    const sup = Object.keys(TARGETS[t].components);
    return `  ${t.padEnd(8)} ${TARGETS[t].root()}  [${sup.join(', ')}]`;
  }).join('\n');
  return `
sarvesh-harness-helper installer — multi-target agent harness installer

Symlinks agents/commands/rules (and optionally skills/hooks/mcp) from this
repository into each harness's global config directory. Always global, always
symlink-based. Not every harness supports every component — unsupported
components are skipped with a note.

Usage:
  node scripts/install.cjs [options]
  shh [options]                           # via 'npm install -g @sarveshkhetan/shh'

Options:
  --target <name>     Target harness: ${TARGET_IDS.join(', ')}, or 'all' (default: all)
  --with <a,b,c>      Additionally include opt-in components: skills, hooks, mcp
  --without <a,b,c>   Exclude default components, e.g. --without rules
  --force             Overwrite existing files/links at the destination
  -y, --yes           Skip confirmation prompt
  -h, --help          Show this help

  --i-understand-the-cache-is-ephemeral
                      Acknowledge that running via 'npx' installs to npm's
                      ephemeral cache; symlinks may break when it is cleaned.
                      Prefer 'npm install -g @sarveshkhetan/shh' + 'shh' for stability.

Components:
${compList}

Targets (and the components each supports):
${tgtList}

Examples:
  node scripts/install.cjs                              # all harnesses: agents+commands+rules+skills
  node scripts/install.cjs --target cursor              # cursor only
  node scripts/install.cjs --without skills             # exclude skills
  node scripts/install.cjs --without rules --force
`;
}

// ---------------------------------------------------------------------------
// Source resolution
// ---------------------------------------------------------------------------

// Canonical source = the directory that contains agents/, commands/, etc.
//   - From a clone:        __dirname = <repo>/scripts          -> source = <repo>
//   - From `npm install -g`: __dirname = <global>/scripts        -> source = <global pkg>
//   - From `npx`:           __dirname = ~/.npm/_npx/<hash>/...  -> source = ephemeral cache
//
// The first two are stable and safe to symlink into. The npx cache is
// ephemeral — symlinks into it break when the cache is cleaned. detectNpx()
// surfaces that to the user.
function resolveSourceRoot() {
  const here = path.resolve(__dirname);
  const candidate = path.dirname(here); // scripts/ -> repo root
  if (fs.existsSync(path.join(candidate, 'agents'))) return candidate;
  if (fs.existsSync(path.join(here, 'agents'))) return here;
  throw new Error(
    `Could not locate the repository root (expected agents/ next to scripts/).\n` +
    `Run this from a clone of sarvesh-harness-helper, or install it globally with:\n` +
    `  npm install -g @sarveshkhetan/shh\n` +
    `then run: shh`
  );
}

// Returns true if the source root is inside npm's ephemeral _npx cache.
// Symlinks pointing there will dangle once the cache is evicted.
function isNpxCache(sourceRoot) {
  return sourceRoot.split(path.sep).includes('_npx');
}

// Read the npm package name from package.json (sibling of the source root)
// so warnings reference the real publish name, not a hardcoded placeholder.
function packageName(sourceRoot) {
  try {
    const pj = JSON.parse(fs.readFileSync(path.join(sourceRoot, 'package.json'), 'utf8'));
    return pj.name || '<package-name>';
  } catch { return '<package-name>'; }
}

// ---------------------------------------------------------------------------
// pi agent frontmatter transform
// ---------------------------------------------------------------------------

// Claude Code agent frontmatter is incompatible with pi-sub-agent:
//   - tool names are Capitalized (Read, Grep, Glob, Bash, Edit, Write) and
//     pi expects lowercase (read, grep, find, bash, edit, write)
//   - `model` uses Claude aliases (opus/sonnet/haiku) that pi can't resolve
//   - `color`, `permissionMode`, `mcpServers` are Claude-specific
//
// This rewrites an agent markdown file into a pi-native one: translates tool
// names, drops the incompatible fields, keeps `name`/`description`/body.
// Returns the transformed file content as a string.

const CLAUDE_TO_PI_TOOLS = {
  Read: 'read',
  Grep: 'grep',
  Glob: 'find',
  Bash: 'bash',
  Edit: 'edit',
  Write: 'write',
};

// Fields to keep in the pi frontmatter; everything else is dropped.
const PI_AGENT_KEEP_FIELDS = new Set(['name', 'description', 'tools']);

function parseFrontmatterBlock(content) {
  // Match leading ---\n...\n--- where the closing fence may be on its own
  // line OR glued to the last value (e.g. `color: blue---` — some agents
  // in the wild have no newline before the closing fence).
  const m = content.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
  if (m) return { frontmatter: m[1], body: content.slice(m[0].length) };
  // Fallback: closing fence glued to last value (color: blue---\n)
  const glued = content.match(/^---\s*\r?\n([\s\S]*?)([A-Za-z]+:.*?)(---\s*(?:\r?\n|$))/);
  if (glued) {
    const frontmatter = glued[2].includes('\n') ? glued[1] + glued[2] : glued[1] + '\n' + glued[2];
    return { frontmatter, body: content.slice(glued[0].length) };
  }
  return { frontmatter: null, body: content };
}

function parseYamlishFrontmatter(raw) {
  // Minimal parser for the flat key:value frontmatter these agents use.
  // Handles: key: value, key: [a, b], key: "value", and simple block lists
  // (key:\n  - item). We only need name/description/tools, so this is enough.
  const result = {};
  const lines = raw.split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const kv = line.match(/^([A-Za-z][\w-]*)\s*:\s*(.*)$/);
    if (!kv) { i++; continue; }
    const key = kv[1];
    let value = kv[2].trim();
    if (value === '') {
      // block list: collect following  - item lines
      const items = [];
      i++;
      while (i < lines.length && /^\s+-\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s+-\s+/, '').trim().replace(/^['"]|['"]$/g, ''));
        i++;
      }
      result[key] = items;
      continue;
    }
    // inline array ["a", "b"] or comma list a, b, c
    if (value.startsWith('[') && value.endsWith(']')) {
      result[key] = value.slice(1, -1).split(',').map(s => s.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean);
    } else {
      result[key] = value.replace(/^['"]|['"]$/g, '');
    }
    i++;
  }
  return result;
}

function transformAgentForPi(content) {
  const { frontmatter, body } = parseFrontmatterBlock(content);
  if (!frontmatter) return content; // no frontmatter, pass through

  const fm = parseYamlishFrontmatter(frontmatter);

  // Translate tools
  let toolsLine = '';
  const rawTools = Array.isArray(fm.tools) ? fm.tools : (typeof fm.tools === 'string' ? fm.tools.split(',') : []);
  const piTools = rawTools.map(t => t.trim()).filter(Boolean).map(t => CLAUDE_TO_PI_TOOLS[t] || t.toLowerCase());
  if (piTools.length > 0) toolsLine = `tools: ${piTools.join(', ')}`;

  // Rebuild frontmatter keeping only name/description/tools
  const lines = ['---'];
  if (fm.name) lines.push(`name: ${fm.name}`);
  if (fm.description) lines.push(`description: ${fm.description}`);
  if (toolsLine) lines.push(toolsLine);
  lines.push('---');

  return lines.join('\n') + '\n' + body;
}

// Directory where generated pi agents are written (inside the package so the
// path is stable for symlinking).
function piAgentsGeneratedDir(sourceRoot) {
  return path.join(sourceRoot, '.generated', 'pi-agents');
}

// Generate pi-native agent files from <sourceRoot>/agents/*.md into
// <sourceRoot>/.generated/pi-agents/*.md. Returns the generated directory path.
// Idempotent: overwrites any existing generated files.
function generatePiAgents(sourceRoot) {
  const srcDir = path.join(sourceRoot, 'agents');
  const outDir = piAgentsGeneratedDir(sourceRoot);
  fs.rmSync(outDir, { recursive: true, force: true });
  ensureDir(outDir);

  const entries = fs.readdirSync(srcDir, { withFileTypes: true });
  let count = 0;
  for (const e of entries) {
    if (!e.isFile() || !e.name.endsWith('.md')) continue;
    const src = path.join(srcDir, e.name);
    const content = fs.readFileSync(src, 'utf8');
    const transformed = transformAgentForPi(content);
    fs.writeFileSync(path.join(outDir, e.name), transformed);
    count++;
  }
  return { outDir, count };
}

// ---------------------------------------------------------------------------
// Plan
// ---------------------------------------------------------------------------

function selectedComponents(opts) {
  const result = [];
  for (const c of COMPONENTS) {
    if (opts.exclude.has(c.id)) continue;
    if (opts.include.has(c.id)) { result.push(c); continue; }
    if (c.defaultOn) result.push(c);
  }
  return result;
}

// Build ops for one target. An op is:
//   { kind: 'link'|'skip', target, component, source, dest, note? }
function buildPlanForTarget(targetId, adapter, components, sourceRoot) {
  const targetRoot = adapter.root();
  const ops = [];

  for (const c of components) {
    const destSubpath = adapter.components[c.id];
    if (!destSubpath) {
      ops.push({ kind: 'skip', target: targetId, component: c.id, source: null, dest: null,
        note: `not supported by ${targetId}` });
      continue;
    }

    const source = path.join(sourceRoot, c.source);
    if (!fs.existsSync(source)) {
      ops.push({ kind: 'skip', target: targetId, component: c.id, source, dest: null,
        note: 'source missing' });
      continue;
    }

    // pi agents: Claude frontmatter is incompatible (Capitalized tools, model
    // aliases, Claude-only fields). Generate pi-native files and link those.
    if (targetId === 'pi' && c.id === 'agents') {
      const { outDir } = generatePiAgents(sourceRoot);
      const entries = fs.readdirSync(outDir, { withFileTypes: true });
      for (const e of entries) {
        if (!e.isFile() || !e.name.endsWith('.md')) continue;
        ops.push({ kind: 'link', target: targetId, component: c.id,
          source: path.join(outDir, e.name), dest: path.join(targetRoot, destSubpath, e.name) });
      }
      continue;
    }

    // Single-file component (hooks, mcp)
    if (!c.walk) {
      ops.push({ kind: 'link', target: targetId, component: c.id, source,
        dest: path.join(targetRoot, destSubpath) });
      continue;
    }

    // Skills: link each immediate child directory that contains SKILL.md
    if (c.extension === null) {
      const entries = fs.readdirSync(source, { withFileTypes: true });
      for (const e of entries) {
        if (!e.isDirectory()) continue;
        const skillMd = path.join(source, e.name, 'SKILL.md');
        if (!fs.existsSync(skillMd)) continue;
        ops.push({ kind: 'link', target: targetId, component: c.id,
          source: path.join(source, e.name), dest: path.join(targetRoot, destSubpath, e.name) });
      }
      continue;
    }

    // agents/commands/rules: link each leaf .md file, preserving subdirs
    const walkDir = (dir, relDir) => {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        const abs = path.join(dir, e.name);
        const rel = path.join(relDir, e.name);
        if (e.isDirectory()) {
          walkDir(abs, rel);
        } else if (e.isFile() && (!c.extension || e.name.endsWith(c.extension))) {
          ops.push({ kind: 'link', target: targetId, component: c.id, source: abs,
            dest: path.join(targetRoot, destSubpath, rel) });
        }
      }
    };
    walkDir(source, '');
  }
  return ops;
}

// ---------------------------------------------------------------------------
// Apply
// ---------------------------------------------------------------------------

function isSymlink(p) {
  try { return fs.lstatSync(p).isSymbolicLink(); } catch { return false; }
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function applyOp(op, force) {
  if (op.kind === 'skip') return { ok: false, skipped: true, note: op.note };

  const { source, dest } = op;

  if (fs.existsSync(dest) || isSymlink(dest)) {
    if (isSymlink(dest)) {
      const existing = fs.readlinkSync(dest);
      const existingAbs = path.resolve(path.dirname(dest), existing);
      if (existingAbs === path.resolve(source)) {
        return { ok: true, skipped: true, note: 'already linked to this source' };
      }
    }
    if (!force) {
      return { ok: false, skipped: true, note: 'exists (use --force to overwrite)' };
    }
    fs.rmSync(dest, { recursive: true, force: true });
  }

  ensureDir(path.dirname(dest));

  // Relative symlink so the repo can be relocated within the filesystem.
  const rel = path.relative(path.dirname(dest), source);
  fs.symlinkSync(rel, dest);
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Reporting
// ---------------------------------------------------------------------------

function printPlan(ops, opts, sourceRoot) {
  console.log(`\nSource (canonical): ${sourceRoot}`);
  console.log(`Mode:               symlink`);
  console.log(`Force:              ${opts.force}`);
  console.log(`Target(s):          ${opts.targets.join(', ')}\n`);

  // Group by target, then by component
  const byTarget = new Map();
  for (const op of ops) {
    if (!byTarget.has(op.target)) byTarget.set(op.target, new Map());
    const byComp = byTarget.get(op.target);
    if (!byComp.has(op.component)) byComp.set(op.component, []);
    byComp.get(op.component).push(op);
  }

  for (const [targetId, byComp] of byTarget) {
    const targetRoot = TARGETS[targetId].root();
    console.log(`── ${targetId}  →  ${targetRoot} ──`);
    for (const [comp, list] of byComp) {
      console.log(`  [${comp}] (${list.length} entr${list.length === 1 ? 'y' : 'ies'})`);
      for (const op of list) {
        const flag = op.kind === 'skip' ? 'SKIP' : 'LINK';
        const relDest = op.dest ? path.relative(targetRoot, op.dest) : '(n/a)';
        const note = op.note ? `  — ${op.note}` : '';
        console.log(`    ${flag}  ${relDest}${note}`);
      }
    }
    console.log();
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  let opts;
  try { opts = parseArgs(process.argv); }
  catch (e) { console.error(e.message); process.exit(2); }

  if (opts.help) { console.log(helpText()); process.exit(0); }

  const sourceRoot = resolveSourceRoot();

  if (isNpxCache(sourceRoot)) {
    const name = packageName(sourceRoot);
    console.error(
      `\n[warning] You ran this via 'npx', so the package is in npm's ephemeral cache:\n` +
      `  ${sourceRoot}\n\n` +
      `This installer creates symlinks that point at the package directory. The npx\n` +
      `cache is cleaned periodically (or by 'npm cache clean'), which would leave\n` +
      `dangling symlinks in ~/.claude/, ~/.cursor/, etc.\n\n` +
      `For a stable install, use the global install instead:\n` +
      `  npm install -g ${name}\n` +
      `  shh\n\n` +
      `To proceed anyway (e.g. for a quick test), re-run with --i-understand-the-cache-is-ephemeral.\n`
    );
    if (!opts.acceptEphemeral) process.exit(2);
    console.error('[warning] Proceeding at your request — symlinks may break when the npx cache is cleaned.\n');
  }

  const components = selectedComponents(opts);

  // Build a combined plan across all selected targets.
  const allOps = [];
  for (const targetId of opts.targets) {
    const adapter = TARGETS[targetId];
    allOps.push(...buildPlanForTarget(targetId, adapter, components, sourceRoot));
  }

  printPlan(allOps, opts, sourceRoot);

  // Confirm unless --yes
  if (!opts.yes) {
    const total = allOps.filter(o => o.kind !== 'skip').length;
    const willOverwrite = allOps.some(o => o.kind !== 'skip' && (fs.existsSync(o.dest) || isSymlink(o.dest)));
    if (!process.stdin.isTTY) {
      console.error('Non-interactive shell: pass -y to confirm.');
      process.exit(2);
    }
    process.stdout.write(`\nApply ${total} operation(s) across ${opts.targets.length} target(s)${willOverwrite ? ' (--force will overwrite)' : ''}? [y/N] `);
    const resp = fs.readFileSync(0, 'utf8').trim().toLowerCase();
    if (resp !== 'y' && resp !== 'yes') { console.log('Aborted.'); process.exit(0); }
  }

  let created = 0, skipped = 0, failed = 0;
  for (const op of allOps) {
    if (op.kind === 'skip') { skipped++; continue; }
    try {
      const r = applyOp(op, opts.force);
      if (r.skipped) skipped++; else created++;
    } catch (e) {
      failed++;
      const targetRoot = TARGETS[op.target].root();
      console.error(`FAIL  [${op.target}] ${path.relative(targetRoot, op.dest)}: ${e.message}`);
    }
  }

  console.log(`\nDone. created=${created} skipped=${skipped} failed=${failed}`);
  if (failed) process.exit(1);
}

main();
