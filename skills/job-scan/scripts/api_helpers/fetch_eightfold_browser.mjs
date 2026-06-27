#!/usr/bin/env node

import { chromium } from "playwright";

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) continue;
    const value = argv[i + 1];
    out[key.slice(2)] = value;
    i += 1;
  }
  return out;
}

const args = parseArgs(process.argv);
const careersUrl = args.url;
if (!careersUrl) {
  console.error("Missing --url");
  process.exit(2);
}

const domain =
  args.domain || new URL(careersUrl).searchParams.get("domain") || "";
const maxStart = Number.parseInt(args.maxStart || "5000", 10);
const pageDelayMs = Number.parseInt(args.pageDelayMs || "350", 10);

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

async function fetchSearchPage(start) {
  const params = new URLSearchParams({
    domain,
    query: "",
    location: "",
    start: String(start),
  });
  const path = `/api/pcsx/search?${params.toString()}&`;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const result = await page.evaluate(async (requestPath) => {
      const response = await fetch(requestPath, {
        credentials: "include",
      });
      return {
        status: response.status,
        text: await response.text(),
      };
    }, path);

    if (result.status === 200) {
      return JSON.parse(result.text);
    }
    if (attempt < 2) {
      await page.waitForTimeout(1000 * (attempt + 1));
      continue;
    }
    throw new Error(`Eightfold browser fetch failed at start=${start}: HTTP ${result.status}`);
  }
}

try {
  await page.goto(careersUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});

  const firstPage = await fetchSearchPage(0);
  const count = ((firstPage.data || {}).count) || 0;
  const aggregated = [ ...(((firstPage.data || {}).positions) || []) ];

  for (let start = 10; start < count && start < maxStart; start += 10) {
    await page.waitForTimeout(pageDelayMs);
    const pageData = await fetchSearchPage(start);
    const positions = ((pageData.data || {}).positions) || [];
    if (!positions.length) break;
    aggregated.push(...positions);
  }

  process.stdout.write(JSON.stringify({
    status: 200,
    error: { message: "", body: "" },
    data: {
      count,
      positions: aggregated,
    },
  }));
} finally {
  await page.close().catch(() => {});
  await browser.close().catch(() => {});
}
