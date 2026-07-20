#!/usr/bin/env node
/**
 * ai-skills-repo installer — Claude Code target.
 *
 * Symlinks agents/, commands/, rules/ (and optionally skills/, hooks.json,
 * mcp-servers.json) from this repository's canonical source directory into
 * ~/.claude/ (always global).
 *
 * Symlinks are used so there is a single source of truth: edit the repo and
 * every linked harness sees the change instantly. There is no copy mode and
 * no project-scope install — this installer is always global + always symlink.
 *
 * Usage:
 *   node scripts/install.cjs                      # agents+commands+rules
 *   node scripts/install.cjs --dry-run            # preview, no changes
 *   node scripts/install.cjs --with skills,hooks,mcp
 *   node scripts/install.cjs --without rules      # skip rules
 *   node scripts/install.cjs --force              # overwrite existing files/links
 *   npx ai-skills-install                         # when published to npm
 *
 * Later targets (cursor, codex, pi) will be added behind --target.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

// ---------------------------------------------------------------------------
// Component registry
// ---------------------------------------------------------------------------

// Each component maps a source (relative to repo root) to a destination (relative
// to ~/.claude). `walk` controls whether the whole subtree is linked file-by-file
// (true) or a single file is linked (false).
const COMPONENTS = [
  {
    id: 'agents',
    source: 'agents',
    dest: 'agents',
    walk: true,
    extension: '.md',
    defaultOn: true,
    description: 'Claude Code subagent definitions (.md).',
  },
  {
    id: 'commands',
    source: 'commands',
    dest: 'commands',
    walk: true,
    extension: '.md',
    defaultOn: true,
    description: 'Slash command definitions (.md).',
  },
  {
    id: 'rules',
    source: 'rules',
    dest: 'rules',
    walk: true,
    extension: '.md',
    defaultOn: true,
    description: 'Language and common rule packs (.md, nested by language).',
  },
  {
    id: 'skills',
    source: 'skills',
    dest: 'skills',
    walk: true,
    extension: null, // link directories (SKILL.md-bearing), not individual files
    defaultOn: false,
    description: 'Portable skills (directories with SKILL.md).',
  },
  {
    id: 'hooks',
    source: 'hooks.json',
    dest: 'hooks.json',
    walk: false,
    defaultOn: false,
    description: 'Hook configuration (hooks.json).',
  },
  {
    id: 'mcp',
    source: 'mcp-servers.json',
    dest: 'mcp-servers.json',
    walk: false,
    defaultOn: false,
    description: 'MCP server catalog (mcp-servers.json).',
  },
];

const TARGETS = ['claude']; // cursor, codex, pi to follow

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = {
    target: 'claude',
    dryRun: false,
    force: false,
    yes: false,
    help: false,
    include: new Set(),
    exclude: new Set(),
  };

  for (let i = 0; i < args.length; i += 1) {
    const a = args[i];
    if (a === '-h' || a === '--help') opts.help = true;
    else if (a === '--dry-run') opts.dryRun = true;
    else if (a === '--force') opts.force = true;
    else if (a === '-y' || a === '--yes') opts.yes = true;
    else if (a === '--target') opts.target = args[++i];
    else if (a === '--with') String(args[++i] || '').split(',').map(s => s.trim()).filter(Boolean).forEach(s => opts.include.add(s));
    else if (a === '--without') String(args[++i] || '').split(',').map(s => s.trim()).filter(Boolean).forEach(s => opts.exclude.add(s));
    else if (a.startsWith('--with=')) a.slice(7).split(',').forEach(s => opts.include.add(s.trim()));
    else if (a.startsWith('--without=')) a.slice(10).split(',').forEach(s => opts.exclude.add(s.trim()));
    else { throw new Error(`Unknown argument: ${a} (see --help)`); }
  }
  return opts;
}

function helpText() {
  const compList = COMPONENTS.map(c => `  ${c.id.padEnd(8)} ${c.defaultOn ? '[default on] ' : '[opt-in]    '}${c.description}`).join('\n');
  return `
ai-skills-repo installer — Claude Code target

Symlinks agents/commands/rules (and optionally skills/hooks/mcp) from this
repository into ~/.claude/ (global). Symlinks keep a single source of truth:
edit the repo and every harness sees the change. Install is always global and
always symlink-based.

Usage:
  node scripts/install.cjs [options]
  npx ai-skills-install [options]

Options:
  --target <name>     Install target. Currently: ${TARGETS.join(', ')} (default: claude)
  --with <a,b,c>      Additionally include opt-in components: skills, hooks, mcp
  --without <a,b,c>   Exclude default components, e.g. --without rules
  --force             Overwrite existing files/links at the destination
  --dry-run           Show the plan without touching the filesystem
  -y, --yes           Skip confirmation prompt
  -h, --help          Show this help

Components:
${compList}

Examples:
  node scripts/install.cjs
  node scripts/install.cjs --dry-run
  node scripts/install.cjs --with skills,hooks --force
  node scripts/install.cjs --without rules
`;
}

// ---------------------------------------------------------------------------
// Source / target resolution
// ---------------------------------------------------------------------------

// Canonical source = the directory that contains agents/, commands/, etc.
// When run from a clone: __dirname = <repo>/scripts  ->  source = <repo>
// When run via npx:      __dirname = <npm-cache>/scripts  ->  source = <npm-cache pkg>
function resolveSourceRoot() {
  const here = path.resolve(__dirname);
  const candidate = path.dirname(here); // scripts/ -> repo root
  if (fs.existsSync(path.join(candidate, 'agents'))) return candidate;
  // Allow running from repo root directly (scripts/install.cjs invoked via cwd)
  if (fs.existsSync(path.join(here, 'agents'))) return here;
  throw new Error(
    `Could not locate the repository root (expected agents/ next to scripts/).\n` +
    `Run this from a clone of ai_skills_repo, or via 'npx ai-skills-install'.`
  );
}

function resolveTargetRoot(target) {
  if (target === 'claude') return path.join(os.homedir(), '.claude');
  throw new Error(`Unsupported target: ${target}. Supported: ${TARGETS.join(', ')}`);
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

// A link op: { kind: 'link'|'skip', component, source, dest, note? }
function buildPlan(components, sourceRoot, targetRoot) {
  const ops = [];
  for (const c of components) {
    const source = path.join(sourceRoot, c.source);
    if (!fs.existsSync(source)) {
      ops.push({ kind: 'skip', component: c.id, source, dest: null, note: 'source missing' });
      continue;
    }

    // Single-file component (hooks, mcp)
    if (!c.walk) {
      const dest = path.join(targetRoot, c.dest);
      ops.push({ kind: 'link', component: c.id, source, dest });
      continue;
    }

    // Directory-walk component
    if (c.extension === null) {
      // Skills: link each immediate child directory that contains SKILL.md
      const entries = fs.readdirSync(source, { withFileTypes: true });
      for (const e of entries) {
        if (!e.isDirectory()) continue;
        const skillMd = path.join(source, e.name, 'SKILL.md');
        if (!fs.existsSync(skillMd)) continue;
        ops.push({ kind: 'link', component: c.id,
          source: path.join(source, e.name), dest: path.join(targetRoot, c.dest, e.name) });
      }
      continue;
    }

    // agents/commands/rules: link each leaf .md file, preserving subdirs (rules/<lang>/...)
    const walkDir = (dir, relDir) => {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        const abs = path.join(dir, e.name);
        const rel = path.join(relDir, e.name);
        if (e.isDirectory()) {
          walkDir(abs, rel);
        } else if (e.isFile() && (!c.extension || e.name.endsWith(c.extension))) {
          ops.push({ kind: 'link', component: c.id,
            source: abs, dest: path.join(targetRoot, c.dest, rel) });
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

  // Destination already exists?
  if (fs.existsSync(dest) || isSymlink(dest)) {
    if (isSymlink(dest)) {
      const existing = fs.readlinkSync(dest);
      const existingAbs = path.resolve(path.dirname(dest), existing);
      if (existingAbs === path.resolve(source)) {
        return { ok: true, skipped: true, note: 'already linked to this source' };
      }
    }
    // exists and is not the right link (or is a real file)
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

function printPlan(ops, opts, sourceRoot, targetRoot) {
  console.log(`\nSource (canonical): ${sourceRoot}`);
  console.log(`Target:             ${targetRoot}`);
  console.log(`Mode:               symlink${opts.dryRun ? ' (dry-run)' : ''}`);
  console.log(`Force:              ${opts.force}\n`);

  const byComp = new Map();
  for (const op of ops) {
    if (!byComp.has(op.component)) byComp.set(op.component, []);
    byComp.get(op.component).push(op);
  }
  for (const [comp, list] of byComp) {
    console.log(`[${comp}] (${list.length} entr${list.length === 1 ? 'y' : 'ies'})`);
    for (const op of list) {
      const flag = op.kind === 'skip' ? 'SKIP' : 'LINK';
      const relDest = path.relative(targetRoot, op.dest || '');
      const note = op.note ? `  — ${op.note}` : '';
      console.log(`  ${flag}  ${relDest}${note}`);
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
  if (!TARGETS.includes(opts.target)) {
    console.error(`Unsupported --target '${opts.target}'. Supported: ${TARGETS.join(', ')}`);
    process.exit(2);
  }

  const sourceRoot = resolveSourceRoot();
  const targetRoot = resolveTargetRoot(opts.target);
  const components = selectedComponents(opts);
  const ops = buildPlan(components, sourceRoot, targetRoot);

  printPlan(ops, opts, sourceRoot, targetRoot);

  if (opts.dryRun) {
    console.log('Dry-run: no changes made.');
    return;
  }

  // Confirm unless --yes
  if (!opts.yes) {
    const total = ops.filter(o => o.kind !== 'skip').length;
    const willOverwrite = ops.some(o => o.kind !== 'skip' && (fs.existsSync(o.dest) || isSymlink(o.dest)));
    if (!process.stdin.isTTY) {
      console.error('Non-interactive shell: pass -y to confirm, or use --dry-run.');
      process.exit(2);
    }
    process.stdout.write(`\nApply ${total} operation(s)${willOverwrite ? ' (--force will overwrite)' : ''}? [y/N] `);
    const resp = fs.readFileSync(0, 'utf8').trim().toLowerCase();
    if (resp !== 'y' && resp !== 'yes') { console.log('Aborted.'); process.exit(0); }
  }

  let created = 0, skipped = 0, failed = 0;
  for (const op of ops) {
    if (op.kind === 'skip') { skipped++; continue; }
    try {
      const r = applyOp(op, opts.force);
      if (r.skipped) skipped++; else created++;
    } catch (e) {
      failed++;
      console.error(`FAIL  ${path.relative(targetRoot, op.dest)}: ${e.message}`);
    }
  }

  console.log(`\nDone. created=${created} skipped=${skipped} failed=${failed}`);
  if (failed) process.exit(1);
}

main();
