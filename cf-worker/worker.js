// TokenPulse global ranking server — Cloudflare Worker + D1
// Endpoints:
//   POST /rank/submit  { handle, tokens_30d, tokens_lifetime }
//   GET  /rank/top?n=20&offset=0
//   GET  /rank/me?handle=<handle>

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const MAX_30D = 50_000_000_000;   // 50B: 1 month sanity cap
const MAX_LT  = 500_000_000_000;  // 500B lifetime sanity cap

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    try {
      if (request.method === 'POST' && pathname === '/rank/submit') {
        return handleSubmit(request, env);
      }
      if (request.method === 'GET' && pathname === '/rank/top') {
        return handleTop(request, env);
      }
      if (request.method === 'GET' && pathname === '/rank/me') {
        return handleMe(request, env);
      }
      return ok({ error: 'not found' }, 404);
    } catch (e) {
      return ok({ error: String(e.message) }, 500);
    }
  },
};

function ok(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

async function handleSubmit(request, env) {
  let body;
  try { body = await request.json(); }
  catch { return ok({ error: 'invalid json' }, 400); }

  const { handle, tokens_30d, tokens_lifetime } = body ?? {};

  const h = (handle ?? '').trim().slice(0, 64);
  if (!h) return ok({ error: 'handle required' }, 400);

  const t30 = Math.floor(Number(tokens_30d ?? 0));
  const tlt = Math.floor(Number(tokens_lifetime ?? 0));
  if (!Number.isFinite(t30) || t30 < 0 || t30 > MAX_30D) {
    return ok({ error: 'tokens_30d out of range' }, 400);
  }
  if (!Number.isFinite(tlt) || tlt < 0 || tlt > MAX_LT) {
    return ok({ error: 'tokens_lifetime out of range' }, 400);
  }

  const now = new Date().toISOString();
  await env.DB.prepare(`
    INSERT INTO scores (handle, tokens_30d, tokens_lifetime, updated_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(handle) DO UPDATE SET
      tokens_30d      = excluded.tokens_30d,
      tokens_lifetime = excluded.tokens_lifetime,
      updated_at      = excluded.updated_at
  `).bind(h, t30, tlt, now).run();

  const rankRow = await env.DB.prepare(
    `SELECT COUNT(*) + 1 AS rank FROM scores WHERE tokens_30d > ?`
  ).bind(t30).first();

  return ok({ ok: true, rank: rankRow?.rank ?? 1 });
}

async function handleTop(request, env) {
  const params = new URL(request.url).searchParams;
  const n      = parseInt(params.get('n')      ?? '20', 10);
  const offset = parseInt(params.get('offset') ?? '0',  10);
  if (!Number.isFinite(n) || n < 1)      return ok({ error: 'invalid n' }, 400);
  if (!Number.isFinite(offset) || offset < 0) return ok({ error: 'invalid offset' }, 400);
  const lim = Math.min(100, n);

  const [rows, totalRow] = await Promise.all([
    // rank is competition rank (count of strictly-higher scores + 1) — the SAME
    // semantics handleMe/handleSubmit use, so a user's rank is identical across
    // every endpoint even with ties.
    env.DB.prepare(`
      SELECT handle, tokens_30d, tokens_lifetime, updated_at,
             (SELECT COUNT(*) FROM scores s2 WHERE s2.tokens_30d > s1.tokens_30d) + 1 AS rank
      FROM scores s1
      ORDER BY tokens_30d DESC
      LIMIT ? OFFSET ?
    `).bind(lim, offset).all(),
    env.DB.prepare(`SELECT COUNT(*) AS c FROM scores`).first(),
  ]);

  return ok({
    rows: rows.results ?? [],
    total: totalRow?.c ?? 0,
  });
}

async function handleMe(request, env) {
  // Truncate to the same 64-char limit handleSubmit stores under, or a long
  // handle would never match its own (truncated) row.
  const handle = (new URL(request.url).searchParams.get('handle') ?? '').trim().slice(0, 64);
  if (!handle) return ok({ error: 'handle required' }, 400);

  const row = await env.DB.prepare(
    `SELECT * FROM scores WHERE handle = ?`
  ).bind(handle).first();

  if (!row) return ok({ found: false });

  const rankRow = await env.DB.prepare(
    `SELECT COUNT(*) + 1 AS rank FROM scores WHERE tokens_30d > ?`
  ).bind(row.tokens_30d).first();

  return ok({ found: true, ...row, rank: rankRow?.rank ?? 1 });
}
