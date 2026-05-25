/**
 * Jobright.ai extraction helpers.
 *
 * These functions run inside the browser via Chrome DevTools MCP evaluate_script.
 * The agent loads this file's content and injects the needed function.
 *
 * Usage from SKILL.md (via evaluate_script):
 *   scrollAndCount()    — scroll to load all job cards, return count
 *   extractJobs()       — extract all visible job cards
 *   resolveUrls(urls)   — resolve Jobright URLs to real ATS URLs
 *   resolveGhEmbed(slug, token) — resolve a Greenhouse embed token via API
 */

// --- 1. Scroll to load all jobs ---
export async function scrollAndCount() {
  let curr = 0;
  for (let i = 0; i < 10; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 2500));
    const now = document.querySelectorAll('a[href*="/jobs/info/"]').length;
    if (now === curr) break;
    curr = now;
  }
  return curr;
}

// --- 2. Extract all job cards ---
export function extractJobs() {
  const links = document.querySelectorAll('a[href*="/jobs/info/"]');
  const seen = new Set();
  return Array.from(links)
    .map(a => {
      const h2 = a.querySelector("h2");
      const title = h2 ? h2.textContent.trim() : "";
      let company = "";
      if (h2 && h2.nextElementSibling) {
        company = h2.nextElementSibling.textContent.trim().split("/")[0].trim();
      }
      const locImg = a.querySelector('img[alt="position"]');
      let location = "";
      if (locImg && locImg.nextElementSibling) {
        location = locImg.nextElementSibling.textContent.trim();
      }
      return { title, company, jobrightUrl: a.href, location };
    })
    .filter(j => j.title && j.jobrightUrl && !seen.has(j.jobrightUrl) && seen.add(j.jobrightUrl));
}

// --- 3. Resolve Jobright URLs → real ATS URLs ---
const ATS_PATTERNS = [
  /https?:\/\/job-boards\.greenhouse\.io\/[a-z0-9-]+\/jobs\/\d+/,
  /https?:\/\/boards\.greenhouse\.io\/[a-z0-9-]+\/jobs\/\d+/,
  /https?:\/\/jobs\.ashbyhq\.com\/[a-z0-9-]+\/[0-9a-f-]{36}/,
  /https?:\/\/jobs\.lever\.co\/[a-z0-9-]+\/[0-9a-f-]{36}/,
  /https?:\/\/[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com\/[^\s"&<]+/,
  /https?:\/\/apply\.workable\.com\/[a-z0-9-]+\/j\/[A-Z0-9]+/,
  /https?:\/\/[a-z0-9-]+\.jobs\.personio\.com\/job\/\d+/,
  /https?:\/\/apply\.careers\.[a-z0-9.-]+\/[^\s"&<]+/,
  /https?:\/\/careers\.[a-z0-9.-]+\/[^\s"<]*(?:job|career)[^\s"&<]*/,
];

const GH_EMBED_RE = /boards\.greenhouse\.io\/embed\/job_app\?token=(\d+)/;

export async function resolveUrls(jobrightUrls) {
  const results = [];
  for (const url of jobrightUrls) {
    try {
      const resp = await fetch(url);
      const text = await resp.text();
      let realUrl = null;
      for (const pat of ATS_PATTERNS) {
        const match = text.match(pat);
        if (match) {
          realUrl = match[0].replace(/&amp;/g, "&");
          break;
        }
      }
      if (!realUrl) {
        const embed = text.match(GH_EMBED_RE);
        if (embed) realUrl = "greenhouse-embed:" + embed[1];
      }
      results.push({ jobrightUrl: url, realUrl });
    } catch {
      results.push({ jobrightUrl: url, realUrl: null });
    }
  }
  return results;
}

// --- 4. Resolve Greenhouse embed token via boards API ---
export async function resolveGhEmbed(slug, token) {
  try {
    const r = await fetch(
      `https://boards-api.greenhouse.io/v1/boards/${slug}/jobs/${token}`
    );
    if (r.ok) {
      const d = await r.json();
      return d.absolute_url || null;
    }
  } catch {
    /* ignore */
  }
  return null;
}
