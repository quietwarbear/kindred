/* Reproducible, synthetic-only Apple and Google store screenshot campaign. */
const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const FRONTEND = path.resolve(__dirname, '..');
const BUILD = path.join(FRONTEND, 'build');
const OUTPUT = path.join(FRONTEND, 'store-assets');
const HOST = '127.0.0.1';
const SENSITIVE_HOST = 'kindred.localhost';
const PORT = Number(process.env.KINDRED_STORE_ASSET_PORT || 4183);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const CAMPAIGN_EVENT_ID = 'store-campaign-reunion';
const CAMPAIGN_INVITATION = 'synthetic-store-campaign-invitation';

const devices = [
  {
    id: 'apple-iphone-6.9',
    directory: path.join('apple', 'iphone-6.9'),
    cssWidth: 440,
    cssHeight: 956,
    deviceScaleFactor: 3,
    outputWidth: 1320,
    outputHeight: 2868,
    captionHeight: 156,
  },
  {
    id: 'apple-ipad-13',
    directory: path.join('apple', 'ipad-13'),
    cssWidth: 1032,
    cssHeight: 1376,
    deviceScaleFactor: 2,
    outputWidth: 2064,
    outputHeight: 2752,
    captionHeight: 172,
  },
  {
    id: 'google-phone',
    directory: path.join('google', 'phone'),
    cssWidth: 360,
    cssHeight: 640,
    deviceScaleFactor: 3,
    outputWidth: 1080,
    outputHeight: 1920,
    captionHeight: 116,
  },
];

const frames = [
  {
    id: 'start-reunion',
    filename: '01-start-reunion.png',
    title: 'Start a family reunion',
    subtitle: 'Name the gathering, dates, and place.',
    alt: 'Kindred reunion setup with synthetic reunion name, dates, organizer, and location.',
  },
  {
    id: 'multiday-itinerary',
    filename: '02-multiday-itinerary.png',
    title: 'Build a multiday itinerary',
    subtitle: 'Keep every activity and update in one plan.',
    alt: 'Kindred multiday reunion itinerary with synthetic welcome, workshop, outing, dinner, and brunch activities.',
  },
  {
    id: 'no-account-rsvp',
    filename: '03-private-rsvp.png',
    title: 'Share one private RSVP',
    subtitle: 'Relatives can answer without creating an account.',
    alt: 'Kindred no-account RSVP choices for a synthetic multiday family reunion.',
  },
  {
    id: 'planning-progress',
    filename: '04-planning-progress.png',
    title: 'See what needs attention',
    subtitle: 'Track responses, gaps, and planning progress.',
    alt: 'Kindred organizer progress view with synthetic RSVP totals and unanswered invitations.',
  },
  {
    id: 'stories-memories',
    filename: '05-stories-memories.png',
    title: 'Keep the stories',
    subtitle: 'Preserve photos, voices, and memories after the reunion.',
    alt: 'Kindred family story prompt containing a clearly synthetic reunion memory.',
  },
];

const syntheticActivities = [
  {
    id: 'arrival',
    title: 'Welcome reception',
    description: 'Reconnect and pick up the weekend plan.',
    start_at: '2027-07-16T17:00:00',
    end_at: '2027-07-16T19:00:00',
    timezone: '',
    venue_name: 'Heritage Hall',
    venue_address: '100 Reunion Way',
    venue_detail: 'Garden room',
    location_tba: false,
    capacity: 80,
    attendance_requested: true,
    visibility: 'published',
    featured: true,
    notes: 'Step-free entrance available.',
  },
  {
    id: 'story-circle',
    title: 'Family story circle',
    description: 'Bring a photograph or a story for younger relatives.',
    start_at: '2027-07-17T10:00:00',
    end_at: '2027-07-17T11:30:00',
    timezone: '',
    venue_name: 'Cedar Room',
    venue_address: '22 Story Lane',
    venue_detail: '',
    location_tba: false,
    capacity: 40,
    attendance_requested: true,
    visibility: 'published',
    featured: false,
    notes: '',
  },
  {
    id: 'picnic',
    title: 'Family picnic',
    description: 'Lunch, games, and family photographs.',
    start_at: '2027-07-17T12:30:00',
    end_at: '2027-07-17T15:30:00',
    timezone: '',
    venue_name: 'Magnolia Park',
    venue_address: '5 Grove Drive',
    venue_detail: 'Pavilion C',
    location_tba: false,
    capacity: null,
    attendance_requested: true,
    visibility: 'published',
    featured: false,
    notes: '',
  },
  {
    id: 'dinner',
    title: 'Celebration dinner',
    description: 'Dinner, acknowledgements, and family history.',
    start_at: '2027-07-17T18:30:00',
    end_at: '2027-07-17T21:30:00',
    timezone: '',
    venue_name: 'Heritage Hall',
    venue_address: '100 Reunion Way',
    venue_detail: 'Main ballroom',
    location_tba: false,
    capacity: 80,
    attendance_requested: true,
    visibility: 'published',
    featured: true,
    notes: '',
  },
  {
    id: 'brunch',
    title: 'Closing brunch',
    description: 'One last meal before everyone travels home.',
    start_at: '2027-07-18T10:00:00',
    end_at: '2027-07-18T12:00:00',
    timezone: '',
    venue_name: 'Cedar Room',
    venue_address: '22 Story Lane',
    venue_detail: '',
    location_tba: false,
    capacity: 60,
    attendance_requested: true,
    visibility: 'published',
    featured: false,
    notes: '',
  },
];

const syntheticEvent = {
  id: CAMPAIGN_EVENT_ID,
  community_id: 'store-campaign-family',
  created_by: 'store-campaign-organizer',
  created_by_name: 'Maya Rivers',
  title: 'The Rivers Family Reunion',
  description: 'A synthetic multiday family reunion created only for store assets.',
  start_at: '2027-07-16T17:00:00',
  end_at: '2027-07-18T12:00:00',
  timezone: 'America/New_York',
  location: 'Cedar Grove, Georgia',
  event_template: 'reunion',
  gathering_format: 'in-person',
  max_attendees: 80,
  agenda: syntheticActivities,
  activity_rsvp_summaries: {
    arrival: { coming: 31, maybe: 3, not_coming: 2, no_response: 8, party_size: 42 },
    'story-circle': { coming: 18, maybe: 4, not_coming: 3, no_response: 19, party_size: 22 },
    picnic: { coming: 28, maybe: 5, not_coming: 2, no_response: 9, party_size: 39 },
    dinner: { coming: 34, maybe: 2, not_coming: 3, no_response: 5, party_size: 48 },
    brunch: { coming: 24, maybe: 6, not_coming: 4, no_response: 10, party_size: 31 },
  },
  event_invites: Array.from({ length: 12 }, (_, index) => ({
    id: `store-campaign-household-${index + 1}`,
    invitee_name: `Rivers household ${index + 1}`,
    email: '',
    rsvp_status: index < 7 ? 'going' : index < 9 ? 'maybe' : 'pending',
    share_message: 'A private family reunion invitation.',
    opened_at: index < 9 ? '2027-06-20T12:00:00Z' : null,
  })),
  rsvp_records: [],
  planning_checklist: [
    { id: 'venue', text: 'Confirm venue', completed: true },
    { id: 'meals', text: 'Finalize meal plan', completed: true },
    { id: 'travel', text: 'Collect travel details', completed: false },
  ],
  volunteer_slots: [
    { id: 'welcome-team', role: 'Welcome table', capacity: 3, assigned_members: ['Maya Rivers', 'Jordan Rivers'] },
  ],
  potluck_items: [
    { id: 'desserts', item: 'Dessert table', quantity_needed: 4, assigned_to: 'Rivers household 2' },
  ],
  assigned_roles: ['Organizer'],
  created_at: '2027-06-15T12:00:00Z',
};

const syntheticOperations = {
  event_id: CAMPAIGN_EVENT_ID,
  timezone: syntheticEvent.timezone,
  total_invitees: 44,
  unanswered_invitations: 8,
  overall: { going: 31, some: 4, maybe: 3, 'not-going': 6 },
  activity_summaries: syntheticEvent.activity_rsvp_summaries,
  day_summaries: {
    '2027-07-16': { coming: 31, maybe: 3, party_size: 42 },
    '2027-07-17': { coming: 34, maybe: 5, party_size: 48 },
    '2027-07-18': { coming: 24, maybe: 6, party_size: 31 },
  },
  activity_rosters: {},
  overlaps: [],
  missing_venue_activity_ids: [],
  recent_changes: [],
};

const syntheticPublicView = {
  invite_id: 'store-campaign-public-view',
  invitee_name: 'Jordan Rivers',
  rsvp_status: 'pending',
  invited_by_name: 'Maya Rivers',
  community_name: 'Rivers family planning space',
  gathering: {
    title: syntheticEvent.title,
    start_at: syntheticEvent.start_at,
    end_at: syntheticEvent.end_at,
    timezone: syntheticEvent.timezone,
    location: syntheticEvent.location,
    event_template: 'reunion',
    gathering_format: 'in-person',
    activity_count: syntheticActivities.length,
    activities: syntheticActivities.map((activity) => ({
      ...activity,
      attendance: syntheticEvent.activity_rsvp_summaries[activity.id],
      my_response: 'no-response',
      response_open: true,
    })),
  },
};

const syntheticPlans = {
  plans: [
    { id: 'seedling', name: 'Seedling', member_limit: 10, monthly_price: 0, annual_price: 0, features: ['Core family space'] },
  ],
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
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) {
    throw new Error('Missing production build. Run npm run build before generating store assets.');
  }
  return new Promise((resolve) => {
    const server = http.createServer((request, response) => {
      const pathname = decodeURIComponent(request.url.split('?')[0]);
      let file = path.join(BUILD, pathname);
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      if (!fs.existsSync(file)) file = path.join(BUILD, 'index.html');
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': mime[path.extname(file)] || 'application/octet-stream',
      });
      fs.createReadStream(file).pipe(response);
    });
    server.listen(PORT, HOST, () => resolve(server));
  });
}

const sessionPayload = {
  token: 'synthetic-store-session',
  user: {
    id: 'store-campaign-organizer',
    full_name: 'Maya Rivers',
    role: 'host',
    community_id: 'store-campaign-family',
    community_ids: ['store-campaign-family'],
    auth_provider: 'email',
    onboarding_completed: true,
  },
  community: { id: 'store-campaign-family', name: 'Rivers family planning space' },
};

function responseHeaders(origin) {
  return {
    'access-control-allow-origin': origin,
    'access-control-allow-credentials': 'true',
    'access-control-allow-headers': 'authorization,content-type',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
  };
}

async function configurePage(page) {
  await page.setBypassServiceWorker(true);
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const requestUrl = new URL(request.url());
    const origin = request.headers().origin || `http://${HOST}:${PORT}`;
    const respondJson = (body, status = 200) => request.respond({
      status,
      contentType: 'application/json',
      headers: responseHeaders(origin),
      body: JSON.stringify(body),
    });

    if (requestUrl.origin === `http://${HOST}:${PORT}` || requestUrl.origin === `http://${SENSITIVE_HOST}:${PORT}`) {
      return request.continue();
    }
    if (requestUrl.origin !== API_ORIGIN) {
      return request.abort();
    }
    if (request.method() === 'OPTIONS') {
      return request.respond({ status: 204, headers: responseHeaders(origin) });
    }
    if (requestUrl.pathname === '/api/auth/me') return respondJson(sessionPayload);
    if (requestUrl.pathname === `/api/events/${CAMPAIGN_EVENT_ID}`) return respondJson(syntheticEvent);
    if (requestUrl.pathname === `/api/events/${CAMPAIGN_EVENT_ID}/operations`) return respondJson(syntheticOperations);
    if (requestUrl.pathname === '/api/community/members') return respondJson({ members: [] });
    if (requestUrl.pathname === '/api/subscriptions/plans') return respondJson(syntheticPlans);
    if (requestUrl.pathname === '/api/public/rsvp') {
      if (request.headers().authorization !== `Bearer ${CAMPAIGN_INVITATION}`) {
        return respondJson({ detail: 'Invitation not found.' }, 404);
      }
      return respondJson(syntheticPublicView);
    }
    return respondJson({ detail: 'Synthetic store campaign route not configured.' }, 404);
  });
}

async function setSession(page, enabled) {
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'networkidle0' });
  await page.evaluate((payload) => {
    if (payload) {
      window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(payload));
    } else {
      window.localStorage.removeItem('gathering-cypher-auth');
    }
    window.localStorage.removeItem('kindred-reunion-draft-v1');
  }, enabled ? sessionPayload : null);
}

async function waitFor(page, selector) {
  await page.waitForSelector(selector, { visible: true, timeout: 20000 });
}

async function installCaption(page, device, frame, targetSelector, endSelector) {
  await waitFor(page, targetSelector);
  await waitFor(page, endSelector);
  const evidence = await page.evaluate(({ captionHeight, deviceId, end, frameData, selector }) => {
    document.getElementById('kindred-store-caption')?.remove();
    document.getElementById('kindred-store-style')?.remove();
    const style = document.createElement('style');
    style.id = 'kindred-store-style';
    style.textContent = `
      html { background: #f7f2e8 !important; }
      body {
        background: #f7f2e8 !important;
        margin: 0 !important;
        overflow: hidden !important;
        overflow-x: hidden !important;
      }
      #kindred-store-caption {
        align-items: flex-start;
        background: linear-gradient(135deg, #172a24 0%, #24473b 100%);
        box-sizing: border-box;
        color: #fffdf7;
        display: flex;
        flex-direction: column;
        height: ${captionHeight}px;
        justify-content: center;
        left: 0;
        padding: 20px 24px 18px;
        position: relative;
        right: 0;
        top: 0;
        z-index: 2147483647;
      }
      #kindred-store-caption strong {
        color: #fffdf7;
        display: block;
        font-family: ui-serif, Georgia, serif;
        font-size: clamp(28px, 7.5vw, 48px);
        font-weight: 650;
        letter-spacing: -0.025em;
        line-height: 1.02;
      }
      #kindred-store-caption span {
        color: #f7d7b0;
        display: block;
        font-family: ui-sans-serif, system-ui, sans-serif;
        font-size: clamp(14px, 3.8vw, 21px);
        font-weight: 650;
        line-height: 1.25;
        margin-top: 8px;
      }
      #kindred-store-app-viewport {
        height: calc(100vh - ${captionHeight}px);
        overflow: hidden;
        position: relative;
        width: 100%;
      }
      * { animation: none !important; transition: none !important; caret-color: transparent !important; }
      ::-webkit-scrollbar { display: none !important; }
    `;
    document.head.appendChild(style);
    const caption = document.createElement('div');
    caption.id = 'kindred-store-caption';
    caption.setAttribute('aria-hidden', 'true');
    caption.innerHTML = `<strong></strong><span></span>`;
    caption.querySelector('strong').textContent = frameData.title;
    caption.querySelector('span').textContent = frameData.subtitle;
    document.body.prepend(caption);

    const target = document.querySelector(selector);
    const endTarget = document.querySelector(end);
    const root = document.getElementById('root');
    const viewport = document.createElement('div');
    viewport.id = 'kindred-store-app-viewport';
    root.before(viewport);
    viewport.appendChild(root);
    window.scrollTo(0, 0);
    const rootScale = 1;
    root.style.transform = '';
    const targetBefore = target.getBoundingClientRect();
    const viewportBefore = viewport.getBoundingClientRect();
    root.style.transform = `translateY(-${Math.max(0, targetBefore.top - viewportBefore.top) / rootScale}px)`;
    const endAfter = endTarget.getBoundingClientRect();
    if (endAfter.bottom < viewportBefore.bottom) {
      const mask = document.createElement('div');
      const backgroundCandidates = [
        endTarget.closest('main'),
        endTarget.closest('.app-canvas'),
        document.querySelector('.App'),
        document.body,
      ].filter(Boolean);
      const background = backgroundCandidates
        .map((element) => getComputedStyle(element).backgroundColor)
        .find((color) => color && color !== 'rgba(0, 0, 0, 0)')
        || '#f7f2e8';
      mask.id = 'kindred-store-bottom-mask';
      mask.style.background = background;
      mask.style.bottom = '0';
      mask.style.left = '0';
      mask.style.position = 'absolute';
      mask.style.right = '0';
      mask.style.top = `${Math.max(0, endAfter.bottom - viewportBefore.top)}px`;
      mask.style.zIndex = '2147483000';
      viewport.appendChild(mask);
    }
    const captionRect = caption.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const titleStyle = getComputedStyle(caption.querySelector('strong'));
    const subtitleStyle = getComputedStyle(caption.querySelector('span'));
    const visibleText = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || !node.textContent.trim()) continue;
      const rect = parent.getBoundingClientRect();
      const styleValue = getComputedStyle(parent);
      if (
        rect.bottom > 0
        && rect.top < Math.min(window.innerHeight, endAfter.bottom)
        && rect.right > 0
        && rect.left < window.innerWidth
        && styleValue.visibility !== 'hidden'
        && styleValue.display !== 'none'
      ) {
        visibleText.push(node.textContent.trim());
      }
    }
    for (const input of document.querySelectorAll('input, textarea')) {
      const rect = input.getBoundingClientRect();
      if (
        rect.bottom > captionHeight
        && rect.top < Math.min(window.innerHeight, endAfter.bottom)
        && rect.right > 0
        && rect.left < window.innerWidth
      ) {
        visibleText.push(input.value || input.placeholder || '');
      }
    }
    return {
      captionRect: {
        top: captionRect.top,
        right: captionRect.right,
        bottom: captionRect.bottom,
        left: captionRect.left,
      },
      targetRect: {
        top: targetRect.top,
        right: targetRect.right,
        bottom: targetRect.bottom,
        left: targetRect.left,
      },
      titleFontSize: parseFloat(titleStyle.fontSize),
      subtitleFontSize: parseFloat(subtitleStyle.fontSize),
      viewport: { width: window.innerWidth, height: window.innerHeight },
      scrollWidth: document.documentElement.scrollWidth,
      visibleText: visibleText.join(' '),
    };
  }, {
    captionHeight: device.captionHeight,
    deviceId: device.id,
    end: endSelector,
    frameData: frame,
    selector: targetSelector,
  });

  const forbidden = [
    /https?:\/\//i,
    /\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b/i,
    /\breviewer\b/i,
    /\bdemo\b/i,
    /\bstaging\b/i,
    /\bdevelopment\b/i,
    /\bgenerated[- ]tool\b/i,
    /\btoken\b/i,
    /\bcredential\b/i,
    /example\.invalid/i,
  ];
  const matched = forbidden.find((pattern) => pattern.test(evidence.visibleText));
  if (matched) throw new Error(`Sensitive or non-store marker visible in ${frame.id}: ${matched}`);
  if (
    evidence.captionRect.top !== 0
    || evidence.captionRect.left !== 0
    || evidence.captionRect.right !== evidence.viewport.width
    || evidence.captionRect.bottom !== device.captionHeight
  ) {
    throw new Error(`Caption safe-area bounds failed for ${device.id}/${frame.id}`);
  }
  if (evidence.titleFontSize < 28 || evidence.subtitleFontSize < 14) {
    throw new Error(`Caption typography is too small for ${device.id}/${frame.id}`);
  }
  if (evidence.scrollWidth > evidence.viewport.width) {
    throw new Error(`Horizontal crop detected for ${device.id}/${frame.id}`);
  }
  if (evidence.targetRect.top < device.captionHeight - 2) {
    throw new Error(
      `Target content is covered by the caption for ${device.id}/${frame.id}: ${JSON.stringify(evidence.targetRect)}`,
    );
  }
  if (evidence.targetRect.right <= 0 || evidence.targetRect.left >= evidence.viewport.width) {
    throw new Error(`Target content is outside the viewport for ${device.id}/${frame.id}`);
  }
}

function pngInfo(file) {
  const bytes = fs.readFileSync(file);
  if (bytes.toString('hex', 1, 4) !== '504e47') throw new Error(`${file} is not a PNG.`);
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
    colorType: bytes[25],
  };
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

async function screenshot(page, device, frame, selector, endSelector = selector) {
  await installCaption(page, device, frame, selector, endSelector);
  const destination = path.join(OUTPUT, device.directory, frame.filename);
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  await page.screenshot({
    path: destination,
    type: 'png',
    captureBeyondViewport: false,
    omitBackground: false,
  });
  const info = pngInfo(destination);
  if (info.width !== device.outputWidth || info.height !== device.outputHeight) {
    throw new Error(`${destination} is ${info.width}x${info.height}; expected ${device.outputWidth}x${device.outputHeight}.`);
  }
  if ([4, 6].includes(info.colorType)) {
    throw new Error(`${destination} contains an alpha channel.`);
  }
  return {
    platform: device.id,
    file: path.relative(OUTPUT, destination),
    width: info.width,
    height: info.height,
    title: frame.title,
    subtitle: frame.subtitle,
    alt: frame.alt,
    sha256: sha256(destination),
  };
}

async function prepareStartFrame(page) {
  await setSession(page, false);
  await page.goto(`http://${HOST}:${PORT}/reunion/start`, { waitUntil: 'networkidle0' });
  await waitFor(page, '[data-testid="reunion-draft-form-card"]');
  await page.type('[data-testid="reunion-name-input"]', syntheticEvent.title);
  await page.$eval('[data-testid="reunion-date-input"]', (element) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(element, '2027-07-16');
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.click('[data-testid="reunion-multiday-toggle"]');
  await page.$eval('[data-testid="reunion-end-date-input"]', (element) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(element, '2027-07-18');
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.type('[data-testid="reunion-organizer-input"]', 'Maya Rivers');
  await page.type('[data-testid="reunion-location-input"]', 'Cedar Grove, Georgia');
}

async function prepareActivationFrame(page) {
  await setSession(page, true);
  await page.goto(`http://${HOST}:${PORT}/reunion/activate/${CAMPAIGN_EVENT_ID}`, { waitUntil: 'networkidle0' });
  await waitFor(page, '[data-testid="reunion-activation-page"]');
}

async function captureDevice(browser, device) {
  const page = await browser.newPage();
  await page.setViewport({
    width: device.cssWidth,
    height: device.cssHeight,
    deviceScaleFactor: device.deviceScaleFactor,
    isMobile: true,
    hasTouch: true,
  });
  await configurePage(page);
  const manifest = [];
  try {
    await prepareStartFrame(page);
    manifest.push(await screenshot(page, device, frames[0], '[data-testid="reunion-draft-form-card"]'));

    await prepareActivationFrame(page);
    manifest.push(await screenshot(
      page,
      device,
      frames[1],
      device.id === 'google-phone'
        ? '[data-testid="itinerary-activity-arrival"]'
        : '[data-testid="reunion-itinerary"]',
      '[data-testid="itinerary-activity-arrival"]',
    ));

    await setSession(page, false);
    await page.goto(`http://${SENSITIVE_HOST}:${PORT}/rsvp#${CAMPAIGN_INVITATION}`, { waitUntil: 'networkidle0' });
    await waitFor(page, '[data-testid="public-rsvp-going"]');
    manifest.push(await screenshot(
      page,
      device,
      frames[2],
      device.id === 'apple-ipad-13' ? 'main' : '[data-testid="public-rsvp-options"]',
      '[data-testid="public-rsvp-options"]',
    ));

    await prepareActivationFrame(page);
    manifest.push(await screenshot(
      page,
      device,
      frames[3],
      device.id === 'apple-ipad-13'
        ? '[data-testid="reunion-summary-cards"]'
        : '[data-testid="reunion-summary-unanswered"]',
      '[data-testid="reunion-attendance-by-day"]',
    ));

    await prepareActivationFrame(page);
    await page.type(
      '[data-testid="reunion-memory-answer"]',
      'Every summer, our family table made room for one more story.',
    );
    manifest.push(await screenshot(page, device, frames[4], '[data-testid="reunion-memory-prompt"]'));
  } finally {
    await page.close();
  }
  return manifest;
}

(async () => {
  const server = await startServer();
  const browser = await puppeteer.launch({
    channel: 'chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });
  try {
    const generated = [];
    for (const device of devices) {
      generated.push(...await captureDevice(browser, device));
    }
    const manifest = {
      generated_at: new Date().toISOString(),
      source: 'Real production frontend build with synthetic disposable in-process API responses.',
      synthetic_data: true,
      published: false,
      files: generated,
    };
    fs.writeFileSync(
      path.join(OUTPUT, 'manifest.json'),
      `${JSON.stringify(manifest, null, 2)}\n`,
      'utf8',
    );
    process.stdout.write(`Generated and validated ${generated.length} synthetic store screenshots.\n`);
  } finally {
    await browser.close();
    server.closeAllConnections?.();
    await new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }
})().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
