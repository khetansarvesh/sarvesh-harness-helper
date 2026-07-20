import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { validateSkills } from './validate-skills.js';

async function createSkill(root, directoryName, frontmatter) {
  const skillDirectory = path.join(root, directoryName);
  await mkdir(skillDirectory);
  await writeFile(
    path.join(skillDirectory, 'SKILL.md'),
    `---\n${frontmatter}\n---\n\n# ${directoryName}\n`,
  );
}

test('accepts a skill whose directory, name, and description are valid', async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), 'validate-skills-'));
  t.after(() => rm(root, { force: true, recursive: true }));
  await createSkill(root, 'portable-skill', 'name: portable-skill\ndescription: A portable skill.');

  assert.deepEqual(validateSkills(root), { errors: [], validCount: 1 });
});

test('reports malformed frontmatter and mismatched skill names', async (t) => {
  const root = await mkdtemp(path.join(tmpdir(), 'validate-skills-'));
  t.after(() => rm(root, { force: true, recursive: true }));
  await createSkill(root, 'wrong-name', 'name: another-name\ndescription: A description.');
  await createSkill(root, 'missing-description', 'name: missing-description');
  await mkdir(path.join(root, 'missing-skill-file'));

  const { errors, validCount } = validateSkills(root);

  assert.equal(validCount, 0);
  assert.deepEqual(errors, [
    'missing-description/SKILL.md - Missing required frontmatter field: description',
    'missing-skill-file/ - Missing SKILL.md',
    'wrong-name/SKILL.md - Frontmatter name "another-name" must match directory name "wrong-name"',
  ]);
});
