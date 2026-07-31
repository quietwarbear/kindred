/* Synthetic, local-only browser campaign for Release 7 guest family access. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-7');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_GUEST_FAMILY_ACCESS_PORT || 4179);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const INVITATION = 'synthetic-release7-invitation-secret';
const CLAIM = 'synthetic-release7-continuity-secret';

const session = {
  token: 'synthetic-release7-account-session',
  user: {
    id: 'synthetic-release7-applicant', full_name: 'Synthetic Applicant',
    email: 'applicant@example.invalid', role: 'member', community_id: '',
    community_ids: [], auth_provider: 'password', onboarding_completed: false,
  },
  community: null,
};

const invitationView = {
  invitee_name: 'Synthetic Guest', invited_by_name: 'Synthetic Organizer',
  community_name: 'Synthetic Family', rsvp_status: 'pending',
  family_access_available: false,
  gathering: {
    title: 'Synthetic Family Reunion', description: 'Local synthetic browser evidence.',
    start_at: '2027-08-14T10:00:00', end_at: '2027-08-15T18:00:00',
    timezone: 'America/Los_Angeles', location: 'Synthetic City',
    event_template: 'reunion', activities: [],
  },
};

const mime = {
  '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2',
};

function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((request, response) => {
      const pathname = decodeURIComponent(request.url.split('?')[0]);
      let file = path.join(BUILD, pathname);
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      if (!fs.existsSync(file)) file = path.join(BUILD, 'index.html');
      response.writeHead(200, { 'Cache-Control': 'no-store', 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(response);
    });
    server.listen(PORT, HOST, () => resolve(server));
  });
}

function jsonResponse(request, body, status = 200) {
  return request.respond({
    status, contentType: 'application/json',
    headers: {
      'access-control-allow-origin': request.headers().origin || `http://${HOST}:${PORT}`,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization,content-type,x-kindred-guest-claim',
      'access-control-allow-methods': 'GET,POST,OPTIONS',
    },
    body: JSON.stringify(body),
  });
}

async function click(page, selector) {
  await page.waitForSelector(selector, { visible: true, timeout: 15000 });
  await page.click(selector);
}

(async () => {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) throw new Error('Run the production frontend build first.');
  fs.mkdirSync(OUTPUT, { recursive: true });
  const server = await startServer();
  const browser = await puppeteer.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const evidence = { errors: [], apiRequests: [], externalRequests: [] };
  let requestStatus = 'pending';

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.setBypassServiceWorker(true);
    page.on('console', (message) => { if (message.type() === 'error') evidence.errors.push(message.text()); });
    page.on('pageerror', (error) => evidence.errors.push(error.message));
    await page.setRequestInterception(true);
    page.on('request', (request) => {
      const requestUrl = new URL(request.url());
      if (request.method() === 'OPTIONS') return jsonResponse(request, {}, 204);
      if (requestUrl.origin === API_ORIGIN) {
        evidence.apiRequests.push({
          method: request.method(), pathname: requestUrl.pathname, search: requestUrl.search,
          authorization: request.headers().authorization || '',
          continuity: request.headers()['x-kindred-guest-claim'] || '',
        });
        if (requestUrl.pathname === '/api/public/rsvp' && request.method() === 'GET') return jsonResponse(request, invitationView);
        if (requestUrl.pathname === '/api/public/rsvp' && request.method() === 'POST') {
          return jsonResponse(request, { ...invitationView, rsvp_status: 'going', saved: true, family_access_available: true });
        }
        if (requestUrl.pathname === '/api/public/family-access-claim') return jsonResponse(request, { claim: CLAIM, expires_in_seconds: 86400 });
        if (requestUrl.pathname === '/api/auth/me') {
          return jsonResponse(request, requestStatus === 'approved' ? {
            ...session,
            user: { ...session.user, community_id: 'synthetic-release7-family', community_ids: ['synthetic-release7-family'], onboarding_completed: true },
            community: { id: 'synthetic-release7-family', name: 'Synthetic Family', lifecycle_state: 'active' },
          } : session);
        }
        if (requestUrl.pathname === '/api/family-access/requests') {
          return jsonResponse(request, { status: 'pending', revision: 0, next_action_codes: ['wait_for_organizer', 'cancel_request'] });
        }
        if (requestUrl.pathname === '/api/family-access/status') {
          return jsonResponse(request, requestStatus === 'approved'
            ? { status: 'approved', revision: 1, next_action_codes: ['open_family_home'], family_space_name: 'Synthetic Family' }
            : { status: 'pending', revision: 0, next_action_codes: ['wait_for_organizer', 'cancel_request'] });
        }
        return jsonResponse(request, {});
      }
      if (requestUrl.origin === `http://${HOST}:${PORT}`) return request.continue();
      evidence.externalRequests.push(request.url());
      return request.abort();
    });

    await page.goto(`http://${HOST}:${PORT}/rsvp#${INVITATION}`, { waitUntil: 'networkidle0' });
    await click(page, '[data-testid="public-rsvp-going"]');
    await click(page, '[data-testid="public-rsvp-continue"]');
    await click(page, '[data-testid="public-rsvp-submit"]');
    await page.waitForSelector('[data-testid="guest-family-access-cta"]', { visible: true });
    await page.screenshot({ path: path.join(OUTPUT, 'guest-rsvp-continuity-mobile.png'), fullPage: true });
    await click(page, '[data-testid="guest-family-access-start"]');
    await page.waitForFunction(() => window.location.pathname === '/login' && window.location.search === '?intent=family-access');
    if (await page.evaluate(() => window.location.hash)) throw new Error('Invitation fragment survived the account boundary.');
    if ((await page.evaluate(() => document.body.innerText)).includes(INVITATION)) throw new Error('Invitation credential rendered in the auth page.');

    await page.evaluate((stored) => window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(stored)), session);
    await page.goto(`http://${HOST}:${PORT}/family/join`, { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => document.body.innerText.includes('Request sent'));
    await page.screenshot({ path: path.join(OUTPUT, 'guest-family-access-pending-mobile.png'), fullPage: true });

    const submission = evidence.apiRequests.find((item) => item.pathname === '/api/family-access/requests');
    if (!submission || submission.continuity !== CLAIM) throw new Error('Continuity claim was not sent only in its dedicated header.');
    for (const item of evidence.apiRequests) {
      if (item.pathname.includes(INVITATION) || item.search.includes(INVITATION) || item.pathname.includes(CLAIM) || item.search.includes(CLAIM)) {
        throw new Error('A private credential appeared in an API URL.');
      }
    }
    const storage = await page.evaluate(() => ({
      local: JSON.stringify(window.localStorage), session: JSON.stringify(window.sessionStorage),
    }));
    if (storage.local.includes(CLAIM) || storage.session.includes(CLAIM)) throw new Error('Continuity claim remained after successful submission.');

    requestStatus = 'approved';
    await click(page, 'button');
    await page.waitForFunction(() => document.body.innerText.includes('Welcome to the family space'));
    if (evidence.errors.length) throw new Error(`Browser errors: ${evidence.errors.join(' | ')}`);
    if (evidence.externalRequests.some((url) => url.includes(INVITATION) || url.includes(CLAIM))) throw new Error('Credential leaked to an external request.');

    console.log(JSON.stringify({
      result: 'passed', invitation_in_api_url: false, claim_in_api_url: false,
      claim_cleared_after_submission: true, pending_and_approved_states_verified: true,
      screenshots: ['guest-rsvp-continuity-mobile.png', 'guest-family-access-pending-mobile.png'],
    }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
