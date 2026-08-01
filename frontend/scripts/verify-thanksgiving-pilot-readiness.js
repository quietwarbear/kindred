/* Synthetic, local-only built-browser campaign for Stage 13. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_THANKSGIVING_PILOT_PORT || 4185);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';

const session = {
  token: 'synthetic-release13-organizer-session',
  user: { id: 'synthetic-organizer', community_id: 'synthetic-family', full_name: 'Synthetic Organizer', role: 'organizer', auth_provider: 'password' },
  community: { id: 'synthetic-family', name: 'Synthetic Family', lifecycle_state: 'active', community_type: 'family' },
};

const confirmations = new Set();
const event = {
  id: 'synthetic-holiday', community_id: 'synthetic-family', title: 'Synthetic holiday dinner',
  description: 'Synthetic organizer walkthrough.', start_at: '2026-11-26T16:00:00-08:00',
  end_at: '2026-11-26T20:00:00-08:00', rsvp_deadline: '2026-11-19T18:00:00-08:00',
  timezone: 'America/Los_Angeles', location: 'Synthetic home', event_template: 'holiday_meal',
  publication_state: 'organizer_draft', gathering_format: 'in-person', max_attendees: 12,
  assigned_roles: ['organizer'], recurrence_frequency: 'none', suggested_contribution: 0,
  event_invites: [], event_role_assignments: [], rsvp_records: [], rsvp_summary: {}, activity_rsvp_summaries: {},
  agenda: [], planning_checklist: [], volunteer_slots: [{ id: 'setup', title: 'Setup', needed_count: 2, assigned_members: [] }],
  potluck_items: [{ id: 'side', item_name: 'Synthetic side', assigned_to: '' }], hidden_from_user_ids: [],
};

function readiness() {
  const required = ['privacy_reviewed', 'guest_plan_reviewed', 'organizer_previewed'];
  const complete = required.filter((code) => confirmations.has(code)).length;
  return {
    pilot_stage: event.publication_state === 'organizer_draft' ? 'draft' : 'ready_to_invite',
    can_finish_setup: complete === required.length,
    required_complete_count: 3 + complete,
    required_total_count: 6,
    next_action_code: complete === required.length ? 'finish_setup' : required[complete],
    aggregate_counts: { active_invitations: 0, responses_received: 0, potluck_items: 1, volunteer_positions: 2 },
    checklist: [
      ['essential_details', true, null], ['schedule_and_timezone', true, null], ['rsvp_window', true, null],
      ...required.map((code) => [code, confirmations.has(code), code]),
      ['food_coordination', true, null], ['reminder_plan_reviewed', false, 'reminder_plan_reviewed'],
      ['invitations_shared', false, 'invitations_shared'],
    ].map(([code, done, action]) => ({ code, status: done ? 'complete' : 'incomplete', required_for_setup: required.includes(code) || ['essential_details', 'schedule_and_timezone', 'rsvp_window'].includes(code), confirmation_action: action })),
  };
}

function eventView() { return { ...event, holiday_pilot_readiness: readiness() }; }

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

(async () => {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) throw new Error('Run the production frontend build first.');
  const server = await startServer();
  const browser = await puppeteer.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const evidence = { errors: [], externalRequests: [], apiUrls: [], checklistBodies: [], inviteMutations: 0, publishMutations: 0 };
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 1000, deviceScaleFactor: 1 });
    page.on('console', (message) => { if (message.type() === 'error') evidence.errors.push(message.text()); });
    page.on('pageerror', (error) => evidence.errors.push(error.message));
    await page.setRequestInterception(true);
    page.on('request', async (request) => {
      const requestUrl = new URL(request.url());
      if (requestUrl.origin === API_ORIGIN) {
        evidence.apiUrls.push({ pathname: requestUrl.pathname, search: requestUrl.search });
        if (request.method() === 'OPTIONS') return jsonResponse(request, {}, 204);
        const apiPath = requestUrl.pathname.replace(/^\/api/, '');
        if (apiPath === '/auth/me') return jsonResponse(request, session);
        if (apiPath === '/events') return jsonResponse(request, [eventView()]);
        if (apiPath === '/gatherings/templates') return jsonResponse(request, { templates: [] });
        if (apiPath === '/subyards') return jsonResponse(request, { subyards: [] });
        if (apiPath === '/community/members') return jsonResponse(request, { members: [{ id: 'synthetic-member', full_name: 'Synthetic Member' }] });
        if (apiPath === '/gatherings/reminders') return jsonResponse(request, { reminders: [] });
        if (apiPath === '/travel-plans') return jsonResponse(request, { travel_plans: [] });
        if (apiPath === '/community/modules') return jsonResponse(request, { enabled: ['gatherings'] });
        if (apiPath === '/communications/unread-summary') return jsonResponse(request, { total_unread: 0 });
        if (apiPath === '/communities/mine') return jsonResponse(request, { communities: [] });
        if (apiPath.endsWith('/holiday-pilot-checklist')) {
          const body = JSON.parse(request.postData() || '{}');
          evidence.checklistBodies.push(body);
          if (body.checked) confirmations.add(body.code); else confirmations.delete(body.code);
          return jsonResponse(request, eventView());
        }
        if (apiPath.endsWith('/publish-holiday-draft')) {
          evidence.publishMutations += 1;
          event.publication_state = 'published';
          return jsonResponse(request, eventView());
        }
        if (apiPath.endsWith('/invites')) evidence.inviteMutations += 1;
        return jsonResponse(request, {});
      }
      if (requestUrl.origin === `http://${HOST}:${PORT}` || requestUrl.protocol === 'data:') return request.continue();
      evidence.externalRequests.push(request.url());
      return request.abort();
    });

    await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((stored) => window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(stored)), session);
    await page.goto(`http://${HOST}:${PORT}/gatherings`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('[data-testid="holiday-pilot-readiness"]', { visible: true });
    const finishInitiallyDisabled = await page.$eval('[data-testid="holiday-pilot-finish-setup"]', (button) => button.disabled);
    if (!finishInitiallyDisabled) throw new Error('Incomplete private draft could finish setup.');

    await page.type('[data-testid="gatherings-invite-guests-input"]', 'one@example.invalid, two@example.invalid');
    await page.click('[data-testid="gatherings-invite-submit-button"]');
    await page.waitForSelector('[data-testid="holiday-invitation-plan-preview"]', { visible: true });
    if (evidence.inviteMutations !== 0) throw new Error('Draft preview created invitation credentials.');

    for (const code of ['privacy_reviewed', 'guest_plan_reviewed', 'organizer_previewed']) {
      await page.click(`[data-testid="holiday-pilot-check-${code}"]`);
      await page.waitForFunction(
        (selector) => document.querySelector(selector)?.className.includes('border-emerald'),
        {},
        `[data-testid="holiday-pilot-check-${code}"]`
      );
    }
    const finishReady = await page.$eval('[data-testid="holiday-pilot-finish-setup"]', (button) => !button.disabled);
    if (!finishReady) throw new Error('Complete checklist did not enable finish setup.');
    await page.click('[data-testid="holiday-pilot-finish-setup"]');
    await page.waitForFunction(() => document.querySelector('[data-testid="holiday-pilot-stage"]').innerText.includes('Ready to invite'));

    if (evidence.publishMutations !== 1) throw new Error('Finish setup was not exactly one explicit mutation.');
    if (evidence.checklistBodies.some((body) => Object.keys(body).some((key) => !['code', 'checked'].includes(key)))) throw new Error('Checklist request included content.');
    if (evidence.apiUrls.some((item) => item.search)) throw new Error('Pilot API request used a query string.');
    if (evidence.externalRequests.length) throw new Error(`Unexpected external requests: ${evidence.externalRequests.join(' | ')}`);
    if (evidence.errors.length) throw new Error(`Browser errors: ${evidence.errors.join(' | ')}`);
    console.log(JSON.stringify({ result: 'passed', private_draft_guard: true, aggregate_invitation_preview: true, explicit_checklist: true, explicit_publish: true, query_strings: false, third_party_requests: false }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
