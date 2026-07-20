#!/usr/bin/env node
/**
 * @sarveshkhetan/shh installer — multi-target agent harness installer.
 *
 * Symlinks agents/, commands/, rules/, skills/, hooks, and mcp config from
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
 *   node scripts/install.cjs                            # claude, agents+commands+rules
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
    defaultOn: false,
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
    },
  },
  cursor: {
    root: () => h('.cursor'),
    components: {
      agents: 'agents',
      rules: 'rules',
      skills: 'skills',
      // cursor has no slash-commands and no hooks; its mcp file is mcp.json
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
    },
  },
  pi: {
    root: () => h('.pi/agent'),
    components: {
      skills: 'skills',
      // pi commands/rules/agents are TypeScript extensions or unsupported as
      // markdown. pi also reads ~/.agents/skills/ but we link the pi-native dir.
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
    targets: ['claude'],
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
  --target <name>     Target harness: ${TARGET_IDS.join(', ')}, or 'all' (default: claude)
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
  node scripts/install.cjs                              # claude: agents+commands+rules
  node scripts/install.cjs --target cursor --with skills
  node scripts/install.cjs --target all --with skills -y
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
