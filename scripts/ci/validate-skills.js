#!/usr/bin/env node
/**
 * Validate public Agent Skills directories and their required frontmatter.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILLS_DIR = path.join(__dirname, '../../skills');

function getFrontmatter(content) {
  const match = content.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
  if (!match) {
    return null;
  }

  return Object.fromEntries(
    match[1]
      .split(/\r?\n/)
      .map(line => line.match(/^([A-Za-z][\w-]*):\s*(.+?)\s*$/))
      .filter(Boolean)
      .map(([, key, value]) => [key, value.replace(/^['"]|['"]$/g, '')]),
  );
}

export function validateSkills(skillsDirectory = SKILLS_DIR) {
  if (!fs.existsSync(skillsDirectory)) {
    return { errors: [], validCount: 0 };
  }

  const directories = fs
    .readdirSync(skillsDirectory, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => entry.name)
    .sort();
  const errors = [];
  let validCount = 0;

  for (const directoryName of directories) {
    const skillMd = path.join(skillsDirectory, directoryName, 'SKILL.md');
    if (!fs.existsSync(skillMd)) {
      errors.push(`${directoryName}/ - Missing SKILL.md`);
      continue;
    }

    let content;
    try {
      content = fs.readFileSync(skillMd, 'utf-8');
    } catch (err) {
      errors.push(`${directoryName}/SKILL.md - ${err.message}`);
      continue;
    }
    if (content.trim().length === 0) {
      errors.push(`${directoryName}/SKILL.md - Empty file`);
      continue;
    }

    const frontmatter = getFrontmatter(content);
    if (!frontmatter) {
      errors.push(`${directoryName}/SKILL.md - Missing YAML frontmatter`);
      continue;
    }
    if (!frontmatter.name) {
      errors.push(`${directoryName}/SKILL.md - Missing required frontmatter field: name`);
      continue;
    }
    if (!frontmatter.description) {
      errors.push(`${directoryName}/SKILL.md - Missing required frontmatter field: description`);
      continue;
    }
    if (frontmatter.name !== directoryName) {
      errors.push(
        `${directoryName}/SKILL.md - Frontmatter name "${frontmatter.name}" must match directory name "${directoryName}"`,
      );
      continue;
    }

    validCount++;
  }

  return { errors, validCount };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { errors, validCount } = validateSkills();
  if (errors.length > 0) {
    for (const error of errors) {
      console.error(`ERROR: ${error}`);
    }
    process.exitCode = 1;
  } else {
    console.log(`Validated ${validCount} public skill directories`);
  }
}
