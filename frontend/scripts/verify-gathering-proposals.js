/* Synthetic, local-only browser campaign for Stage 9 gathering proposals. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-9');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_GATHERING_PROPOSALS_PORT || 4181);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const REFERENCE = 'a'.repeat(32);

const organizerSession = {
  token: 'synthetic-release9-organizer-session',
  user: { id: 'synthetic-organizer', community_id: 'synthetic-family', full_name: 'Synthetic Organizer', role: 'organizer', auth_provider: 'password' },
  community: { id: 'synthetic-family', name: 'Synthetic Family', lifecycle_state: 'active' },
};
const memberSession = {
  token: 'synthetic-release9-member-session',
  user: { id: 'synthetic-member', community_id: 'synthetic-family', full_name: 'Synthetic Member', role: 'member', auth_provider: 'password' },
  community: organizerSession.community,
};

let pulse = {
  proposal_reference: REFERENCE, state: 'submitted', revision: 0,
  working_title: 'Summer family picnic', gathering_type: 'day_trip',
  broad_date_window: 'Early summer', location_suggestion: 'Near the family home',
  organizer_note: 'A private synthetic organizer note.', proposer_display_name: 'Synthetic Member',
  proposer_tombstone: false, is_mine: false,
  interest: { aggregate: { interested: 0, maybe: 0, not_available: 0, total: 0 }, my_response: 'none', my_revision: 0 },
};
let ownSubmission = null;

const mime = { '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

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
  return request.respond({ status, contentType: 'application/json', headers: {
    'access-control-allow-origin': request.headers().origin || `http://${HOST}:${PORT}`,
    'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization,content-type',
    'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS',
  }, body: JSON.stringify(body) });
}

async function seedSession(page, session) {
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((stored) => window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(stored)), session);
}

async function clickButton(page, label) {
  const clicked = await page.evaluate((text) => {
    const button = Array.from(document.querySelectorAll('button')).find((item) => item.textContent.trim().includes(text));
    if (button) button.click();
    return Boolean(button);
  }, label);
  if (!clicked) throw new Error(`Button not found: ${label}`);
}

function memberPulse() {
  const { organizer_note, proposer_display_name, proposer_tombstone, ...safe } = pulse;
  return { ...safe, is_mine: false };
}

async function configurePage(page, session, evidence) {
  page.on('console', (message) => { if (message.type() === 'error') evidence.errors.push(message.text()); });
  page.on('pageerror', (error) => evidence.errors.push(error.message));
  await page.setRequestInterception(true);
  page.on('request', async (request) => {
    const requestUrl = new URL(request.url());
    if (requestUrl.origin === API_ORIGIN) {
      evidence.apiRequests.push({ method: request.method(), pathname: requestUrl.pathname, search: requestUrl.search });
      if (request.method() === 'OPTIONS') return jsonResponse(request, {});
      const apiPath = requestUrl.pathname.replace(/^\/api/, '');
      if (apiPath === '/auth/me') return jsonResponse(request, session);
      if (apiPath === '/community/modules') return jsonResponse(request, { enabled: [] });
      if (apiPath === '/communications/unread-summary') return jsonResponse(request, { announcements_unread: 0, chat_unread: 0, total_unread: 0 });
      if (apiPath === '/communities/mine') return jsonResponse(request, { communities: [] });
      if (apiPath === '/gathering-proposals/organizer/review') return jsonResponse(request, {
        proposals: [pulse, ...(ownSubmission ? [{ ...ownSubmission, proposer_display_name: 'Synthetic Member', organizer_note: 'Keep this note private.' }] : [])],
        eligible_organizers: [{ organizer_reference: 'synthetic-organizer', display_name: 'Synthetic Organizer', role: 'organizer' }],
      });
      if (apiPath === '/gathering-proposals' && request.method() === 'GET') return jsonResponse(request, { proposals: [memberPulse(), ...(ownSubmission ? [ownSubmission] : [])] });
      if (apiPath === '/gathering-proposals' && request.method() === 'POST') {
        const data = JSON.parse(request.postData() || '{}');
        evidence.submissionBodyOnly = !requestUrl.search && Boolean(data.working_title) && Boolean(data.organizer_note);
        ownSubmission = {
          proposal_reference: 'b'.repeat(32), state: 'submitted', revision: 0,
          working_title: data.working_title, gathering_type: data.gathering_type,
          broad_date_window: data.broad_date_window, location_suggestion: data.location_suggestion,
          organizer_note: data.organizer_note, is_mine: true,
          interest: { aggregate: { interested: 0, maybe: 0, not_available: 0, total: 0 }, my_response: 'none', my_revision: 0 },
        };
        return jsonResponse(request, ownSubmission);
      }
      if (apiPath.endsWith('/publish')) {
        pulse = { ...pulse, state: 'published', revision: 1 };
        return jsonResponse(request, pulse);
      }
      if (apiPath.endsWith('/interest')) {
        const data = JSON.parse(request.postData() || '{}');
        evidence.interestBodyOnly = !requestUrl.search && ['interested', 'maybe', 'not_available'].includes(data.response);
        pulse = { ...pulse, interest: { aggregate: { interested: 1, maybe: 0, not_available: 0, total: 1 }, my_response: data.response, my_revision: 1 } };
        return jsonResponse(request, memberPulse());
      }
      if (apiPath.endsWith('/conversion-preview')) {
        const data = JSON.parse(request.postData() || '{}');
        return jsonResponse(request, { proposal_state: 'published', proposal_revision: 1, preview_digest: 'c'.repeat(64), proposal: {
          new_gathering: { title: data.title, start_at: data.start_at, end_at: data.end_at, timezone: data.timezone, location: data.location, gathering_format: data.gathering_format, max_attendees: data.max_attendees, organizer_display_name: 'Synthetic Organizer', publication_state: 'organizer_draft' },
          guarantees: { zero_invitations: true, zero_responses: true, zero_assignments: true, zero_memories: true, no_proposer_identity: true, new_structural_identifiers: true },
        } });
      }
      if (apiPath.endsWith('/convert')) {
        evidence.conversionCount += 1;
        return jsonResponse(request, { status: 'draft_created', proposal_state: 'converted', next_action: 'continue_planning', planning_path: '/reunion/command/synthetic-release9-private-draft' });
      }
      return jsonResponse(request, {});
    }
    if (requestUrl.origin === `http://${HOST}:${PORT}` || requestUrl.protocol === 'data:') return request.continue();
    evidence.externalRequests.push(request.url());
    return request.abort();
  });
}

(async () => {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) throw new Error('Run the production frontend build first.');
  fs.mkdirSync(OUTPUT, { recursive: true });
  const server = await startServer();
  const browser = await puppeteer.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const evidence = { errors: [], apiRequests: [], externalRequests: [], submissionBodyOnly: false, interestBodyOnly: false, conversionCount: 0 };
  try {
    const organizerPage = await browser.newPage();
    await organizerPage.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await configurePage(organizerPage, organizerSession, evidence);
    await seedSession(organizerPage, organizerSession);
    await organizerPage.goto(`http://${HOST}:${PORT}/proposals`, { waitUntil: 'networkidle0' });
    await organizerPage.waitForSelector(`[data-testid="proposal-card-${REFERENCE}"]`, { visible: true });
    await clickButton(organizerPage, 'Publish interest pulse');
    await organizerPage.waitForFunction(() => document.body.innerText.includes('Open family interest pulse'));
    await clickButton(organizerPage, 'Preview private draft');
    await organizerPage.evaluate(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      const inputs = Array.from(document.querySelectorAll('input[type="datetime-local"]'));
      setter.call(inputs[0], '2028-06-03T10:00'); inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      setter.call(inputs[1], '2028-06-03T18:00'); inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
    });
    await clickButton(organizerPage, 'Review exact draft');
    await organizerPage.waitForSelector('[data-testid="proposal-conversion-preview"]', { visible: true });
    await organizerPage.screenshot({ path: path.join(OUTPUT, 'organizer-proposal-review-desktop.png'), fullPage: true });

    const memberPage = await browser.newPage();
    await memberPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await configurePage(memberPage, memberSession, evidence);
    await seedSession(memberPage, memberSession);
    await memberPage.goto(`http://${HOST}:${PORT}/proposals`, { waitUntil: 'networkidle0' });
    await memberPage.waitForSelector(`[data-testid="proposal-card-${REFERENCE}"]`, { visible: true });
    const memberText = await memberPage.$eval('body', (element) => element.innerText);
    if (memberText.includes('private synthetic organizer note') || memberText.includes('Suggested by')) throw new Error('Member pulse exposed organizer-only fields.');
    await clickButton(memberPage, 'Interested');
    await memberPage.waitForFunction(() => document.body.innerText.includes('Your response: Interested'));
    await clickButton(memberPage, 'Suggest a gathering');
    await memberPage.type('[data-testid="proposal-submission-form"] input', 'Family history day');
    await memberPage.type('[data-testid="proposal-submission-form"] textarea', 'A private note for organizers only.');
    await clickButton(memberPage, 'Submit privately');
    await memberPage.waitForFunction(() => document.body.innerText.includes('Private organizer review'));
    await memberPage.screenshot({ path: path.join(OUTPUT, 'member-interest-pulse-mobile.png'), fullPage: true });

    organizerPage.removeAllListeners('console'); organizerPage.removeAllListeners('pageerror');
    await clickButton(organizerPage, 'Create one private draft');
    await organizerPage.waitForFunction(() => window.location.pathname === '/reunion/command/synthetic-release9-private-draft');

    if (!evidence.submissionBodyOnly || !evidence.interestBodyOnly) throw new Error('Private proposal or interest data was not body-only.');
    if (evidence.conversionCount !== 1) throw new Error('Conversion was not one explicit action.');
    if (evidence.apiRequests.some((item) => item.search)) throw new Error('Stage 9 API request used a query string.');
    if (evidence.externalRequests.length) throw new Error(`Unexpected external requests: ${evidence.externalRequests.join(' | ')}`);
    if (evidence.errors.length) throw new Error(`Browser errors: ${evidence.errors.join(' | ')}`);
    console.log(JSON.stringify({ result: 'passed', private_submission: true, anonymous_aggregates_and_own_response: true, organizer_preview: true, explicit_single_conversion: true, screenshots: ['organizer-proposal-review-desktop.png', 'member-interest-pulse-mobile.png'] }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
