const HARD_EXPIRED_PATTERNS = [
  /job (is )?no longer available/i,
  /job.*no longer open/i,
  /position has been filled/i,
  /this job has expired/i,
  /job posting has expired/i,
  /no longer accepting applications/i,
  /this (position|role|job) (is )?no longer/i,
  /this job (listing )?is closed/i,
  /job (listing )?not found/i,
  /the page you are looking for doesn.t exist/i,
  /diese stelle (ist )?(nicht mehr|bereits) besetzt/i,
  /offre (expirée|n'est plus disponible)/i,
];

const LISTING_PAGE_PATTERNS = [
  /\d+\s+jobs?\s+found/i,
  /search for jobs page is loaded/i,
];

const EXPIRED_URL_PATTERNS = [
  /[?&]error=true/i,
];

const APPLY_PATTERNS = [
  /\bapply\b/i,
  /\bsolicitar\b/i,
  /\bbewerben\b/i,
  /\bpostuler\b/i,
  /submit application/i,
  /easy apply/i,
  /start application/i,
  /ich bewerbe mich/i,
];

const MIN_CONTENT_CHARS = 300;

function firstMatch(patterns, text = '') {
  return patterns.find((pattern) => pattern.test(text));
}

function hasApplyControl(controls = []) {
  return controls.some((control) => APPLY_PATTERNS.some((pattern) => pattern.test(control)));
}

/**
 * Check if a redirect lost the job-specific identifier from the URL.
 * e.g., greenhouse.io/figma/jobs/4756707004 → figma.com/careers/ = expired
 */
function redirectLostJobId(originalUrl = '', finalUrl = '') {
  if (!originalUrl || !finalUrl || originalUrl === finalUrl) return false;
  const JOB_ID_PATTERNS = [
    /\/jobs?\/\d{4,}/,                                    // /jobs/12345
    /\/details\/\d{4,}/,                                  // /details/200123
    /[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/, // UUID
    /\/j\/[A-Z0-9]{6,}/,                                  // Workable /j/ABC123
    /\/job\/[^/]+_[A-Z0-9]+/,                              // Workday /job/..._R12345
  ];
  const originalHasId = JOB_ID_PATTERNS.some(p => p.test(originalUrl));
  const finalHasId = JOB_ID_PATTERNS.some(p => p.test(finalUrl));
  return originalHasId && !finalHasId;
}

export function classifyLiveness({ status = 0, originalUrl = '', finalUrl = '', bodyText = '', applyControls = [] } = {}) {
  if (status === 404 || status === 410) {
    return { result: 'expired', reason: `HTTP ${status}` };
  }

  // Redirect lost the job ID — expired job redirected to general careers page
  if (redirectLostJobId(originalUrl, finalUrl)) {
    return { result: 'expired', reason: `redirect lost job ID: ${originalUrl} → ${finalUrl}` };
  }

  const expiredUrl = firstMatch(EXPIRED_URL_PATTERNS, finalUrl);
  if (expiredUrl) {
    return { result: 'expired', reason: `redirect to ${finalUrl}` };
  }

  const expiredBody = firstMatch(HARD_EXPIRED_PATTERNS, bodyText);
  if (expiredBody) {
    return { result: 'expired', reason: `pattern matched: ${expiredBody.source}` };
  }

  if (hasApplyControl(applyControls)) {
    return { result: 'active', reason: 'visible apply control detected' };
  }

  const listingPage = firstMatch(LISTING_PAGE_PATTERNS, bodyText);
  if (listingPage) {
    return { result: 'expired', reason: `pattern matched: ${listingPage.source}` };
  }

  if (bodyText.trim().length < MIN_CONTENT_CHARS) {
    return { result: 'expired', reason: 'insufficient content — likely nav/footer only' };
  }

  return { result: 'uncertain', reason: 'content present but no visible apply control found' };
}
