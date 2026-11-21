import { execFile } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { promisify } from 'node:util';
import { answerResearchQuestion, researchChatConfig, ResearchChatError } from './research-chat.mjs';

const SESSION_MS = 30 * 60 * 1000;
const MAX_BODY = 1024;
const COOKIE = '__Host-stock_team_local';
const runFile = promisify(execFile);
const PORTFOLIO_SCRIPT = fileURLToPath(new URL('./portfolio.py', import.meta.url));
const STATIC_FILES = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/privacy', ['privacy.html', 'text/html; charset=utf-8']],
  ['/style.css', ['style.css', 'text/css; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
]);
const PORTFOLIO = {
  buyingPower: { krw: 15_000_000, usd: 4200 },
  holdings: [
    { symbol: 'NVDA', name: '엔비디아', quantity: 20, marketValue: 3640, currency: 'USD', returnPct: 12.3 },
    { symbol: 'MSFT', name: '마이크로소프트', quantity: 8, marketValue: 3580, currency: 'USD', returnPct: -2.4 },
    { symbol: '005930', name: '삼성전자', quantity: 80, marketValue: 4_770_000, currency: 'KRW', returnPct: 6.8 },
  ],
};
const ALERT = {
  symbol: 'ANT', state: 'waiting', close: 98.20, threshold: 99, minimumLow: 93,
  requiredSessions: 2, matchedSessions: 0,
};
const DEMO_RATES = new Map([
  ['KOSPI', { currency: 'KRW', commissionBps: 1.5, taxBps: 20 }],
  ['KOSDAQ', { currency: 'KRW', commissionBps: 1.5, taxBps: 20 }],
  ['US', { currency: 'USD', commissionBps: 10, taxBps: 0.206 }],
]);

const HEADERS = {
  'Cache-Control': 'no-store',
  'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'",
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Resource-Policy': 'same-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-Robots-Tag': 'noindex, nofollow, noarchive',
};

function reply(res, status, payload, headers = {}) {
  const isBytes = Buffer.isBuffer(payload);
  res.writeHead(status, {
    ...HEADERS,
    'Content-Type': 'application/json; charset=utf-8',
    ...headers,
  });
  res.end(isBytes ? payload : JSON.stringify(payload));
}

function sessionCookie(token, seconds) {
  return `${COOKIE}=${token}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=${seconds}`;
}

function tokenFrom(req) {
  const candidate = req.headers.cookie?.split(';').find((cookie) => cookie.trimStart().startsWith(`${COOKIE}=`));
  const token = candidate?.trim().slice(COOKIE.length + 1);
  return /^[A-Za-z0-9_-]{43}$/.test(token ?? '') ? token : null;
}

async function jsonBody(req) {
  const contentType = req.headers['content-type']?.split(';', 1)[0]?.trim().toLowerCase();
  if (contentType !== 'application/json' || req.headers['content-encoding']) return { status: 415 };
  if (Number(req.headers['content-length']) > MAX_BODY) return { status: 413 };

  let bytes = 0;
  const chunks = [];
  for await (const chunk of req.iterator({ destroyOnReturn: false })) {
    bytes += chunk.length;
    if (bytes > MAX_BODY) return { status: 413 };
    chunks.push(chunk);
  }
  try {
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    return body && typeof body === 'object' && !Array.isArray(body) ? { body } : { status: 400 };
  } catch {
    return { status: 400 };
  }
}

function demoFee({ market, amount }) {
  const rates = DEMO_RATES.get(market);
  if (!rates || typeof amount !== 'number' || !Number.isFinite(amount) ||
      amount <= 0 || amount > 1_000_000_000_000) return null;
  const units = rates.currency === 'KRW' ? 1 : 100;
  if (Math.abs(amount * units - Math.round(amount * units)) > 0.00001) return null;
  const commission = Math.round(amount * units * rates.commissionBps / 10_000);
  const tax = Math.round(amount * units * rates.taxBps / 10_000);
  return {
    currency: rates.currency, amount, commission: commission / units, tax: tax / units,
    estimatedCost: (commission + tax) / units,
  };
}

function personalPortfolioReader(env) {
  const { STOCK_TEAM_PYTHON, STOCK_TEAM_LOCAL_STATE, STOCK_TEAM_ACCOUNT } = env;
  const { TOSSINVEST_CLIENT_ID, TOSSINVEST_CLIENT_SECRET } = env;
  if (!STOCK_TEAM_PYTHON || !STOCK_TEAM_LOCAL_STATE || !TOSSINVEST_CLIENT_ID || !TOSSINVEST_CLIENT_SECRET) return null;

  return async (signal) => {
    const childEnv = {
      TOSSINVEST_CLIENT_ID,
      TOSSINVEST_CLIENT_SECRET,
      STOCK_TEAM_LOCAL_STATE,
      PYTHONIOENCODING: 'utf-8',
    };
    if (STOCK_TEAM_ACCOUNT) childEnv.STOCK_TEAM_ACCOUNT = STOCK_TEAM_ACCOUNT;
    const { stdout } = await runFile(STOCK_TEAM_PYTHON, [PORTFOLIO_SCRIPT], {
      env: childEnv, encoding: 'utf8', timeout: 45_000, maxBuffer: 256 * 1024, signal,
    });
    return JSON.parse(stdout);
  };
}

export function makeServer({
  now = Date.now,
  researchAnswer = answerResearchQuestion,
  researchEnv = {},
  readPortfolio = null,
} = {}) {
  const staticFiles = new Map([...STATIC_FILES].map(([path, [file, type]]) => [
    path, { payload: readFileSync(new URL(`./public/${file}`, import.meta.url)), type },
  ]));
  const sessions = new Map();
  const mode = readPortfolio ? 'personal' : 'demo';
  const router = researchChatConfig(researchEnv).mode;
  let pendingPortfolio = false;

  function state(consented) {
    return { consented, mode, router, portfolioEnabled: true };
  }

  function endSession(token) {
    const session = sessions.get(token);
    if (!session) return;
    session.abort.abort();
    sessions.delete(token);
  }

  function forgetExpired() {
    const timestamp = now();
    for (const [token, session] of sessions) {
      if (session.expires <= timestamp) endSession(token);
    }
  }

  function currentToken(req) {
    const token = tokenFrom(req);
    const session = sessions.get(token);
    if (session && session.expires > now()) return token;
    endSession(token);
    return null;
  }

  async function servePortfolio(req, res, token) {
    if (!readPortfolio) return reply(res, 200, PORTFOLIO);
    if (pendingPortfolio) return reply(res, 409, { error: 'portfolio_in_progress' });
    pendingPortfolio = true;
    try {
      const result = await readPortfolio(sessions.get(token).abort.signal);
      if (currentToken(req) !== token) return reply(res, 403, { error: 'consent_required' });
      if (result.error) {
        const denied = result.error === 'toss_access_denied';
        return reply(res, denied ? 502 : 503, { error: denied ? result.error : 'portfolio_unavailable' });
      }
      return reply(res, 200, result);
    } catch {
      if (currentToken(req) !== token) return reply(res, 403, { error: 'consent_required' });
      return reply(res, 503, { error: 'portfolio_unavailable' });
    } finally {
      pendingPortfolio = false;
    }
  }

  async function serveChat(req, res, token, body) {
    const session = sessions.get(token);
    if (session.answering) return reply(res, 409, { error: 'answer_in_progress' });
    if (Object.keys(body).length !== 1 || typeof body.question !== 'string') {
      return reply(res, 400, { error: 'invalid_question' });
    }
    session.answering = true;
    try {
      const answer = await researchAnswer(body, {
        env: researchEnv, sampleAlert: ALERT, signal: session.abort.signal,
      });
      if (currentToken(req) !== token) return reply(res, 403, { error: 'consent_required' });
      return reply(res, 200, answer);
    } catch (error) {
      if (currentToken(req) !== token) return reply(res, 403, { error: 'consent_required' });
      if (error instanceof ResearchChatError) return reply(res, error.status, { error: error.code });
      return reply(res, 503, { error: 'answer_unavailable' });
    } finally {
      session.answering = false;
    }
  }

  const server = createServer({ requestTimeout: 10_000, headersTimeout: 5_000, maxHeaderSize: 8192 }, async (req, res) => {
    try {
      const host = `localhost:${server.address().port}`;
      if (req.headers.host !== host) return reply(res, 403, { error: 'host_denied' });
      const path = req.url ?? '';
      if (path.includes('?')) return reply(res, 404, { error: 'not_found' });
      const token = currentToken(req);

      if (req.method === 'GET') {
        const file = staticFiles.get(path);
        if (file) return reply(res, 200, file.payload, { 'Content-Type': file.type });
        if (path === '/healthz') return reply(res, 200, { status: 'ok', mode: 'local' });
        if (path === '/api/state') return reply(res, 200, state(Boolean(token)));
        if (path === '/api/portfolio' || path === '/api/alert') {
          if (!token || (req.headers['sec-fetch-site'] && req.headers['sec-fetch-site'] !== 'same-origin')) {
            return reply(res, 403, { error: 'consent_required' });
          }
          return path === '/api/alert' ? reply(res, 200, ALERT) : await servePortfolio(req, res, token);
        }
      }

      if (req.method !== 'POST' || !['/api/consent', '/api/disconnect', '/api/fee', '/api/chat'].includes(path)) {
        return reply(res, 404, { error: 'not_found' });
      }
      if (req.headers.origin !== `http://${host}`) return reply(res, 403, { error: 'origin_denied' });

      const { body, status } = await jsonBody(req);
      if (status) return reply(res, status, { error: 'invalid_body' }, { Connection: 'close' });
      const activeToken = currentToken(req);

      if (path === '/api/consent') {
        if (Object.keys(body).length !== 1 || body.accepted !== true) {
          return reply(res, 400, { error: 'explicit_consent_required' });
        }
        if (activeToken) return reply(res, 200, state(true));
        forgetExpired();
        if (sessions.size >= 32) return reply(res, 429, { error: 'demo_busy' });
        const newToken = randomBytes(32).toString('base64url');
        sessions.set(newToken, { expires: now() + SESSION_MS, answering: false, abort: new AbortController() });
        return reply(res, 200, state(true), { 'Set-Cookie': sessionCookie(newToken, SESSION_MS / 1000) });
      }

      if (path === '/api/disconnect') {
        if (Object.keys(body).length !== 0) return reply(res, 400, { error: 'invalid_request' });
        endSession(activeToken);
        return reply(res, 200, state(false), { 'Set-Cookie': sessionCookie('', 0) });
      }

      if (!activeToken) return reply(res, 403, { error: 'consent_required' });
      if (path === '/api/chat') return await serveChat(req, res, activeToken, body);
      const fee = Object.keys(body).length === 2 && demoFee(body);
      if (!fee) return reply(res, 400, { error: 'invalid_scenario' });
      return reply(res, 200, fee);
    } catch {
      if (!res.headersSent && !res.destroyed) reply(res, 500, { error: 'server_error' });
    }
  });

  server.maxRequestsPerSocket = 200;
  server.keepAliveTimeout = 5_000;
  const cleanup = setInterval(forgetExpired, 60_000);
  cleanup.unref();
  server.once('close', () => clearInterval(cleanup));
  return server;
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const { RESEARCH_CHAT_PROVIDER, BIZROUTER_API_KEY } = process.env;
  const server = makeServer({
    readPortfolio: personalPortfolioReader(process.env),
    researchEnv: { RESEARCH_CHAT_PROVIDER, BIZROUTER_API_KEY },
  });
  server.listen(0, '127.0.0.1', () => process.stdout.write(`http://localhost:${server.address().port}/\n`));
  process.once('SIGTERM', () => server.close());
}
