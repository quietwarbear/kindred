/* Browser smoke test and screenshot capture for anonymous commercial flows. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots');
const HOST = '127.0.0.1';
const SENSITIVE_HOST = 'kindred.localhost';
const PORT = 4173;
const API_URL = 'https://kindred-production-badd.up.railway.app/api/subscriptions/plans';
const API_ORIGIN = new URL(API_URL).origin;

const mockActivities = [
  {
    id: 'welcome',
    title: 'Welcome reception',
    description: 'Arrive, reconnect, and pick up the weekend schedule.',
    start_at: '2027-07-18T17:00:00',
    end_at: '2027-07-18T19:00:00',
    timezone: '',
    venue_name: 'Heritage Hall',
    venue_address: '100 Reunion Way',
    venue_detail: 'Main ballroom',
    location_tba: false,
    capacity: 80,
    attendance_requested: true,
    visibility: 'published',
    featured: true,
    notes: 'Casual dress. Step-free entrance is on the east side.',
  },
  {
    id: 'workshop',
    title: 'Heritage workshop',
    description: 'Bring a photograph or a story you want younger relatives to know.',
    start_at: '2027-07-19T10:00:00',
    end_at: '2027-07-19T11:30:00',
    timezone: '',
    venue_name: 'Community Arts Center',
    venue_address: '22 Story Lane',
    venue_detail: 'Studio 2',
    location_tba: false,
    capacity: 30,
    attendance_requested: true,
    visibility: 'published',
    notes: 'Large-print prompt cards will be available.',
  },
  {
    id: 'outing',
    title: 'Park outing',
    description: 'An easy afternoon outside with games and family photos.',
    start_at: '2027-07-19T11:00:00',
    end_at: '2027-07-19T14:00:00',
    timezone: '',
    venue_name: 'Lakeside Park',
    venue_address: '5 Lake Drive',
    venue_detail: 'Pavilion C',
    location_tba: false,
    capacity: null,
    attendance_requested: true,
    visibility: 'published',
    notes: 'Bring water and sun protection.',
  },
  {
    id: 'dinner',
    title: 'Formal dinner',
    description: 'Dinner, acknowledgements, and the family history presentation.',
    start_at: '2027-07-19T18:30:00',
    end_at: '2027-07-20T00:30:00',
    timezone: '',
    venue_name: 'Riverside Hotel',
    venue_address: '400 River Street',
    venue_detail: 'Grand room',
    location_tba: false,
    capacity: 6,
    attendance_requested: true,
    visibility: 'published',
    notes: 'Semi-formal. Shuttle departs Heritage Hall at 5:45 PM.',
  },
  {
    id: 'brunch-draft',
    title: 'Closing brunch',
    description: '',
    start_at: '2027-07-20T10:00:00',
    end_at: '2027-07-20T12:00:00',
    timezone: '',
    venue_name: '',
    venue_address: '',
    venue_detail: '',
    location_tba: true,
    capacity: null,
    attendance_requested: true,
    visibility: 'draft',
    notes: '',
  },
];

const mockEvent = {
  id: 'demo',
  community_id: 'local-demo-community',
  created_by: 'local-demo-host',
  created_by_name: 'Avery Organizer',
  title: 'The Johnson Family Reunion',
  description: 'A private multiday family reunion.',
  start_at: '2027-07-18T09:00:00',
  end_at: '2027-07-20T18:00:00',
  timezone: 'America/Los_Angeles',
  location: 'Oakland, California',
  event_template: 'reunion',
  gathering_format: 'in-person',
  max_attendees: 80,
  agenda: mockActivities,
  activity_rsvp_summaries: {
    welcome: { coming: 4, maybe: 1, not_coming: 0, no_response: 1, party_size: 6 },
    workshop: { coming: 3, maybe: 1, not_coming: 0, no_response: 2, party_size: 4 },
    outing: { coming: 2, maybe: 2, not_coming: 0, no_response: 2, party_size: 3 },
    dinner: { coming: 5, maybe: 1, not_coming: 0, no_response: 0, party_size: 7 },
    'brunch-draft': { coming: 0, maybe: 0, not_coming: 0, no_response: 6, party_size: 0 },
  },
  event_invites: Array.from({ length: 6 }, (_, index) => ({
    id: `invite-${index}`,
    invitee_name: `Invited household ${index + 1}`,
    email: `household${index + 1}@example.invalid`,
    rsvp_status: index < 4 ? 'going' : 'pending',
    share_message: 'Synthetic local browser-verification invitation.',
  })),
  rsvp_records: [],
  planning_checklist: [],
  volunteer_slots: [],
  potluck_items: [],
  assigned_roles: ['Organizer'],
  created_at: '2027-07-01T12:00:00Z',
};

const mockOperations = {
  event_id: 'demo',
  timezone: mockEvent.timezone,
  total_invitees: 6,
  unanswered_invitations: 2,
  overall: { going: 3, some: 1, maybe: 1, 'not-going': 1 },
  activity_summaries: mockEvent.activity_rsvp_summaries,
  day_summaries: {
    '2027-07-18': { coming: 4, maybe: 1, party_size: 6 },
    '2027-07-19': { coming: 5, maybe: 2, party_size: 7 },
  },
  activity_rosters: {
    welcome: [{ row_key: 'welcome:guest-1', display_name: 'A. Guest', status: 'coming', party_size: 2, updated_at: '2027-07-10T12:00:00Z' }],
  },
  overlaps: [['workshop', 'outing']],
  missing_venue_activity_ids: [],
  recent_changes: [{ row_key: 'welcome:guest-1', display_name: 'A. Guest', status: 'coming', updated_at: '2027-07-10T12:00:00Z' }],
};

const mockPublicView = {
  invite_id: 'demo-invite',
  invitee_name: 'Invited Guest',
  rsvp_status: 'pending',
  invited_by_name: 'Avery Organizer',
  community_name: 'Johnson reunion planning space',
  gathering: {
    title: mockEvent.title,
    start_at: mockEvent.start_at,
    end_at: mockEvent.end_at,
    timezone: mockEvent.timezone,
    location: mockEvent.location,
    event_template: 'reunion',
    gathering_format: 'in-person',
    activity_count: 4,
    activities: mockActivities
      .filter((activity) => activity.visibility === 'published')
      .map((activity) => ({
        ...activity,
        attendance: mockEvent.activity_rsvp_summaries[activity.id],
        my_response: 'no-response',
        response_open: true,
      })),
  },
};

const mime = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const pathname = decodeURIComponent(req.url.split('?')[0]);
      let file = path.join(BUILD, pathname);
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      if (!fs.existsSync(file)) file = path.join(BUILD, 'index.html');
      res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(PORT, HOST, () => resolve(server));
  });
}

async function assertVisible(page, selector, message) {
  try {
    await page.waitForSelector(selector, { visible: true, timeout: 15000 });
  } catch (error) {
    const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 1200));
    throw new Error(`${message}\nURL: ${page.url()}\nRendered text: ${bodyText}`, { cause: error });
  }
  if (!(await page.$(selector))) throw new Error(message);
}

async function assertSensitivePageIsolation(page, externalRequests, label) {
  const evidence = await page.evaluate(async () => {
    const scriptSources = [...document.scripts]
      .map((script) => script.src)
      .filter(Boolean)
      .filter((src) => new URL(src).origin !== window.location.origin);
    const cachedRsvpRequests = [];
    for (const cacheName of await caches.keys()) {
      const cache = await caches.open(cacheName);
      for (const request of await cache.keys()) {
        if (new URL(request.url).pathname.startsWith('/rsvp')) {
          cachedRsvpRequests.push(request.url);
        }
      }
    }
    return {
      documentReferrer: document.referrer,
      referrerPolicy: document.querySelector('meta[name="referrer"]')?.content || '',
      scriptSources,
      cachedRsvpRequests,
    };
  });
  if (
    evidence.documentReferrer
    || evidence.referrerPolicy !== 'no-referrer'
    || evidence.scriptSources.length
    || evidence.cachedRsvpRequests.length
    || externalRequests.length
  ) {
    throw new Error(`${label} isolation regressed: ${JSON.stringify({
      ...evidence,
      externalRequests,
    })}`);
  }
}

(async () => {
  const liveResponse = await fetch(API_URL);
  if (!liveResponse.ok) throw new Error(`Live plans API returned ${liveResponse.status}`);
  const livePlans = await liveResponse.text();
  const livePayload = JSON.parse(livePlans);
  const expectedAmounts = {
    sapling: { monthly: 9.99, annual: 89.99 },
    oak: { monthly: 19.99, annual: 179.99 },
    redwood: { monthly: 39.99, annual: 359.99 },
  };
  for (const [tier, expected] of Object.entries(expectedAmounts)) {
    const plan = livePayload.plans.find((candidate) => candidate.id === tier);
    const monthly = plan?.billing_options?.monthly?.amount ?? plan?.monthly_price;
    const annual = plan?.billing_options?.annual?.amount ?? plan?.annual_price;
    if (monthly !== expected.monthly || annual !== expected.annual) {
      throw new Error(`Live API pricing drift for ${tier}: monthly=${monthly}, annual=${annual}`);
    }
  }
  const server = await startServer();
  const browser = await puppeteer.launch({
    channel: 'chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    fs.mkdirSync(OUTPUT, { recursive: true });
    const page = await browser.newPage();
    const browserErrors = [];
    const anonymousMutationRequests = [];
    const invitationApiRequests = [];
    const sensitiveExternalRequests = [];
    let sensitiveCapturePhase = '';
    const allowedSensitiveOrigins = new Set([
      `http://${SENSITIVE_HOST}:${PORT}`,
      API_ORIGIN,
    ]);
    const handleRequest = (request) => {
      const requestUrl = new URL(request.url());
      const pageOrigin = request.headers().origin || `http://${HOST}:${PORT}`;
      const respondJson = (body) => request.respond({
        status: 200,
        contentType: 'application/json',
        headers: {
          'access-control-allow-origin': pageOrigin,
          'access-control-allow-credentials': 'true',
          'access-control-allow-headers': 'authorization,content-type',
          'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
        },
        body: JSON.stringify(body),
      });
      if (
        sensitiveCapturePhase
        && ['http:', 'https:'].includes(requestUrl.protocol)
        && !allowedSensitiveOrigins.has(requestUrl.origin)
      ) {
        sensitiveExternalRequests.push({
          phase: sensitiveCapturePhase,
          url: request.url(),
        });
        return request.abort();
      }
      if (request.url().startsWith(API_ORIGIN) && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
        anonymousMutationRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
      if (request.url() === API_URL) {
        request.respond({
          status: 200,
          contentType: 'application/json',
          headers: {
            'access-control-allow-origin': `http://${HOST}:${PORT}`,
            'access-control-allow-credentials': 'true',
          },
          body: livePlans,
        });
      } else if (requestUrl.origin === API_ORIGIN && requestUrl.pathname === '/api/auth/me') {
        respondJson({
          token: 'local-browser-verification',
          user: {
            id: 'local-demo-host',
            full_name: 'Avery Organizer',
            role: 'host',
            auth_provider: 'email',
            onboarding_completed: true,
          },
          community: { id: 'local-demo-community', name: 'Local verification' },
        });
      } else if (requestUrl.origin === API_ORIGIN && requestUrl.pathname === '/api/events/demo') {
        respondJson(mockEvent);
      } else if (requestUrl.origin === API_ORIGIN && requestUrl.pathname === '/api/events/demo/operations') {
        respondJson(mockOperations);
      } else if (requestUrl.origin === API_ORIGIN && requestUrl.pathname === '/api/community/members') {
        respondJson({ members: [] });
      } else if (requestUrl.origin === API_ORIGIN && requestUrl.pathname === '/api/public/rsvp') {
        if (request.method() === 'OPTIONS') {
          return request.respond({
            status: 204,
            headers: {
              'access-control-allow-origin': pageOrigin,
              'access-control-allow-headers': 'authorization,content-type',
              'access-control-allow-methods': 'GET,POST,OPTIONS',
            },
          });
        }
        const authorization = request.headers().authorization || '';
        invitationApiRequests.push({
          method: request.method(),
          pathname: requestUrl.pathname,
          search: requestUrl.search,
          authorization,
        });
        if (authorization !== 'Bearer demo-invite') {
          return request.respond({
            status: 401,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Missing invitation credential.' }),
          });
        }
        respondJson(mockPublicView);
      } else if (requestUrl.pathname === '/sw.js') {
        request.abort();
      } else {
        request.continue();
      }
    };
    const configurePage = async (targetPage) => {
      targetPage.on('console', (message) => {
        if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`);
      });
      targetPage.on('pageerror', (error) => browserErrors.push(`page: ${error.message}`));
      await targetPage.setBypassServiceWorker(true);
      await targetPage.setRequestInterception(true);
      targetPage.on('request', handleRequest);
    };
    await configurePage(page);

    await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="landing-primary-cta"]', 'Reunion start CTA is missing.');
    const headline = await page.$eval('[data-testid="landing-headline"]', (element) => element.innerText);
    if (headline !== 'Plan the reunion. Bring everyone in. Keep the stories.') {
      throw new Error(`Unexpected reunion headline: ${headline}`);
    }
    await assertVisible(page, '[data-testid="landing-see-all-plans-link"]', 'Public plans link is missing.');
    await assertVisible(page, '[data-testid="landing-billing-notice"]', 'Homepage billing suspension notice is missing.');
    await assertVisible(page, '[data-testid="landing-interface-evidence"]', 'Real reunion interface evidence is missing.');
    if (await page.$('[data-testid="landing-read-strategy-link"]')) throw new Error('Consumer strategy link still exists.');
    await assertVisible(page, '[data-testid="public-plan-seedling"]', 'Canonical landing prices did not render.');
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-home-desktop.png'), fullPage: true });

    await page.focus('[data-testid="landing-primary-cta"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => window.location.pathname === '/reunion/start');
    await assertVisible(page, '[data-testid="reunion-draft-form-card"]', 'Public reunion draft form did not open.');
    await page.type('[data-testid="reunion-name-input"]', 'The Johnson Family Reunion');
    await page.$eval('[data-testid="reunion-date-input"]', (element) => {
      const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      valueSetter.call(element, '2027-07-18');
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.click('[data-testid="reunion-multiday-toggle"]');
    await assertVisible(page, '[data-testid="reunion-end-date-input"]', 'Optional reunion end date did not appear.');
    await page.$eval('[data-testid="reunion-end-date-input"]', (element) => {
      const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      valueSetter.call(element, '2027-07-20');
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.type('[data-testid="reunion-organizer-input"]', 'Avery Johnson');
    await page.type('[data-testid="reunion-location-input"]', 'Oakland, California');
    await page.click('[data-testid="reunion-create-draft-button"]');
    await assertVisible(page, '[data-testid="reunion-draft-workspace"]', 'Useful reunion draft did not render.');
    const draftText = await page.$eval('[data-testid="reunion-draft-workspace"]', (element) => element.innerText);
    const timezoneValue = await page.$eval('[data-testid="reunion-timezone-input"]', (element) => element.value);
    if (!draftText.includes('2027-07-20') || !timezoneValue || !draftText.includes(timezoneValue)) {
      throw new Error('Multiday range or primary timezone is missing from the draft.');
    }
    await page.click('[data-testid="reunion-preview-button"]');
    await assertVisible(page, '[data-testid="reunion-invitation-preview"]', 'Invitation preview did not render.');
    await assertVisible(page, '[data-testid="reunion-account-boundary-link"]', 'Authentication boundary is missing.');
    const accountHref = await page.$eval('[data-testid="reunion-account-boundary-link"]', (element) => element.getAttribute('href'));
    if (accountHref !== '/login?intent=reunion') throw new Error(`Unexpected reunion account boundary: ${accountHref}`);
    if (anonymousMutationRequests.length) {
      throw new Error(`Anonymous reunion draft made backend mutations: ${anonymousMutationRequests.join(', ')}`);
    }
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-draft-desktop.png'), fullPage: true });

    await page.goto(`http://${HOST}:${PORT}/pricing`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="public-pricing-page"]', 'Public pricing route did not open.');
    await assertVisible(
      page,
      '[data-testid="web-subscription-unavailable"]',
      'The web subscription suspension notice is missing.',
    );
    for (const tier of ['seedling', 'sapling', 'oak', 'redwood', 'elder-grove']) {
      await assertVisible(page, `[data-testid="public-plan-${tier}"]`, `Missing ${tier} on public pricing.`);
    }
    await assertVisible(page, '[data-testid="public-plan-price-seedling-free"]', 'Seedling is not explicitly free.');
    for (const tier of ['sapling', 'oak', 'redwood']) {
      await assertVisible(page, `[data-testid="public-plan-price-${tier}-monthly"]`, `Missing ${tier} monthly price.`);
      await assertVisible(page, `[data-testid="public-plan-price-${tier}-annual"]`, `Missing ${tier} annual price.`);
    }
    const pricingText = await page.$eval('[data-testid="public-pricing-page"]', (element) => element.innerText);
    for (const amount of ['$9.99', '$89.99', '$19.99', '$179.99', '$39.99', '$359.99']) {
      if (!pricingText.includes(amount)) throw new Error(`Public pricing is missing ${amount}.`);
    }
    if (!pricingText.includes('Billed every month') || !pricingText.includes('Billed once per year')) {
      throw new Error('Public pricing does not disclose both billing intervals.');
    }
    if (!pricingText.includes('Web subscriptions are temporarily unavailable while billing is being updated.')) {
      throw new Error('Public pricing does not explain that web subscription purchasing is unavailable.');
    }
    await page.screenshot({ path: path.join(OUTPUT, 'public-pricing-desktop.png'), fullPage: true });

    await page.evaluate(() => {
      window.localStorage.setItem('gathering-cypher-auth', JSON.stringify({
        token: 'local-browser-verification',
        user: {
          id: 'local-demo-host',
          full_name: 'Avery Organizer',
          role: 'host',
          auth_provider: 'email',
          onboarding_completed: true,
        },
        community: { id: 'local-demo-community', name: 'Local verification' },
      }));
    });
    await page.goto(`http://${HOST}:${PORT}/reunion/activate/demo`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="reunion-itinerary"]', 'Organizer itinerary did not render.');
    await assertVisible(page, '[data-testid="reunion-operations"]', 'Reunion operations summary did not render.');
    const itineraryText = await page.$eval('[data-testid="reunion-itinerary"]', (element) => element.innerText);
    for (const expected of ['Welcome reception', 'Heritage workshop', 'Park outing', 'Formal dinner', 'Overlaps', 'Draft']) {
      if (!itineraryText.includes(expected)) throw new Error(`Organizer itinerary is missing ${expected}.`);
    }
    await page.click('[data-testid="itinerary-add-button"]');
    await assertVisible(page, '[data-testid="itinerary-activity-form"]', 'Organizer activity form did not open.');
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-itinerary-desktop.png'), fullPage: true });

    await page.evaluate(() => window.localStorage.removeItem('gathering-cypher-auth'));
    sensitiveExternalRequests.length = 0;
    sensitiveCapturePhase = 'fragment-desktop';
    await page.goto(`http://${SENSITIVE_HOST}:${PORT}/rsvp#demo-invite`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="public-rsvp-some"]', 'Partial-reunion response is missing.');
    await page.click('[data-testid="public-rsvp-some"]');
    await page.click('[data-testid="public-rsvp-continue"]');
    await page.waitForFunction(() => document.body.innerText.includes('Tell us which activities'));
    await assertVisible(page, '[data-testid="public-rsvp-itinerary"]', 'Combined public activity RSVP did not render.');
    const publicItineraryText = await page.$eval('[data-testid="public-rsvp-itinerary"]', (element) => element.innerText);
    if (!publicItineraryText.includes('Who') && !publicItineraryText.includes('coming')) {
      throw new Error('Public itinerary does not show privacy-safe attendance counts.');
    }
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-public-rsvp-desktop.png'), fullPage: true });
    await assertSensitivePageIsolation(page, sensitiveExternalRequests, 'Fragment RSVP route');
    sensitiveCapturePhase = '';
    if (
      invitationApiRequests.length < 1
      || invitationApiRequests.some((request) => (
        request.pathname !== '/api/public/rsvp'
        || request.search
        || request.authorization !== 'Bearer demo-invite'
      ))
    ) {
      throw new Error(`Invitation credential transport regressed: ${JSON.stringify(invitationApiRequests)}`);
    }

    invitationApiRequests.length = 0;
    sensitiveExternalRequests.length = 0;
    sensitiveCapturePhase = 'legacy-desktop';
    const legacyPage = await browser.newPage();
    await configurePage(legacyPage);
    await legacyPage.goto(`http://${SENSITIVE_HOST}:${PORT}/rsvp/demo-invite`, { waitUntil: 'networkidle0' });
    await legacyPage.waitForFunction(
      () => window.location.pathname === '/rsvp' && window.location.hash === '#demo-invite',
    );
    await assertVisible(legacyPage, '[data-testid="public-rsvp-some"]', 'Legacy invitation transition did not render.');
    await assertSensitivePageIsolation(legacyPage, sensitiveExternalRequests, 'Legacy RSVP route');
    sensitiveCapturePhase = '';
    if (
      invitationApiRequests.length !== 1
      || invitationApiRequests[0].pathname !== '/api/public/rsvp'
      || invitationApiRequests[0].search
      || invitationApiRequests[0].authorization !== 'Bearer demo-invite'
    ) {
      throw new Error(`Legacy invitation did not transition to header transport: ${JSON.stringify(invitationApiRequests)}`);
    }
    await legacyPage.close();

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="landing-see-all-plans-link"]', 'Mobile plans link is missing.');
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-home-mobile.png'), fullPage: true });

    await page.evaluate(() => {
      window.localStorage.setItem('kindred-reunion-draft-v1', JSON.stringify({
        gathering_name: 'The Johnson Family Reunion',
        approximate_date: '2027-07-18',
        end_date: '2027-07-20',
        timezone: 'America/Los_Angeles',
        multiday_enabled: true,
        organizer_name: 'Avery Johnson',
        location: 'Oakland, California',
      }));
    });
    await page.goto(`http://${HOST}:${PORT}/reunion/start`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="reunion-draft-workspace"]', 'Mobile reunion draft did not render.');
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-draft-mobile.png'), fullPage: true });

    await page.evaluate(() => {
      window.localStorage.setItem('gathering-cypher-auth', JSON.stringify({
        token: 'local-browser-verification',
        user: { id: 'local-demo-host', full_name: 'Avery Organizer', role: 'host', auth_provider: 'email', onboarding_completed: true },
        community: { id: 'local-demo-community', name: 'Local verification' },
      }));
    });
    await page.goto(`http://${HOST}:${PORT}/reunion/activate/demo`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="reunion-itinerary"]', 'Mobile organizer itinerary did not render.');
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-itinerary-mobile.png'), fullPage: true });

    await page.evaluate(() => window.localStorage.removeItem('gathering-cypher-auth'));
    invitationApiRequests.length = 0;
    sensitiveExternalRequests.length = 0;
    sensitiveCapturePhase = 'fragment-mobile';
    await page.goto(`http://${SENSITIVE_HOST}:${PORT}/rsvp#demo-invite`, { waitUntil: 'networkidle0' });
    await page.click('[data-testid="public-rsvp-some"]');
    await page.click('[data-testid="public-rsvp-continue"]');
    await assertVisible(page, '[data-testid="public-rsvp-itinerary"]', 'Mobile public activity RSVP did not render.');
    if (invitationApiRequests.some((request) => request.pathname.includes('demo-invite') || request.search)) {
      throw new Error(`Mobile invitation credential appeared in an API URL: ${JSON.stringify(invitationApiRequests)}`);
    }
    await assertSensitivePageIsolation(page, sensitiveExternalRequests, 'Mobile fragment RSVP route');
    sensitiveCapturePhase = '';
    await page.screenshot({ path: path.join(OUTPUT, 'reunion-public-rsvp-mobile.png'), fullPage: true });

    await page.goto(`http://${HOST}:${PORT}/pricing`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="public-plan-redwood"]', 'Mobile pricing did not render.');
    await page.screenshot({ path: path.join(OUTPUT, 'public-pricing-mobile.png'), fullPage: true });

    for (const route of ['/privacy', '/terms', '/support']) {
      await page.goto(`http://${HOST}:${PORT}${route}`, { waitUntil: 'networkidle0' });
      if (page.url().includes('/login')) throw new Error(`${route} unexpectedly required authentication.`);
      if ((await page.evaluate(() => document.body.innerText.length)) < 500) {
        throw new Error(`${route} did not render enough public content.`);
      }
    }
    if (browserErrors.length) {
      throw new Error(`Browser errors detected:\n${browserErrors.join('\n')}`);
    }

    console.log('Verified reunion-first homepage, keyboard CTA, browser-only multiday draft, invitation preview, organizer itinerary, operations summary, combined public activity RSVP, authentication boundary, public pricing, privacy, terms, and support at desktop/mobile widths with no browser errors or anonymous backend mutations.');
    console.log(`Screenshots: ${OUTPUT}`);
  } finally {
    await browser.close();
    server.closeAllConnections?.();
    await new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
