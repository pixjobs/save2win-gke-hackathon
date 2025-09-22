// app/api/game-state/route.js
export const dynamic = 'force-dynamic';

import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import http from 'node:http';
import https from 'node:https';

const ENGINE_URL =
  process.env.ENGINE_URL ||
  'http://save2win-engine.boa.svc.cluster.local/api/v1/game-state';

const agent = ENGINE_URL.startsWith('https:')
  ? new https.Agent({ keepAlive: true, timeout: 30_000 })
  : new http.Agent({  keepAlive: true, timeout: 30_000 });

export async function GET(req) {
  // Prefer the HttpOnly cookie we set in /api/oauth
  const token = cookies().get('boa_id_token')?.value;
  // Allow explicit Authorization header (useful for curl/testing)
  const headerAuth = req.headers.get('authorization');
  const authHeader = token ? `Bearer ${token}` : headerAuth;

  if (!authHeader) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  const controller = new AbortController();
  const to = setTimeout(() => controller.abort(), 10_000);

  try {
    const resp = await fetch(ENGINE_URL, {
      headers: { authorization: authHeader },
      cache: 'no-store',
      // @ts-ignore — Node runtime
      agent,
      signal: controller.signal,
    });

    clearTimeout(to);

    if (resp.status === 401 || resp.status === 403) {
      const text = await safeText(resp);
      return NextResponse.json(
        { error: 'Unauthorized when calling engine', details: text || undefined },
        { status: resp.status }
      );
    }

    if (!resp.ok) {
      const text = await safeText(resp);
      return NextResponse.json(
        { error: 'Failed to fetch game state from engine', status: resp.status, details: text || undefined },
        { status: resp.status }
      );
    }

    const data = await resp.json();
    return NextResponse.json(data);

  } catch (err) {
    clearTimeout(to);
    const isAbort = err?.name === 'AbortError';
    return NextResponse.json(
      { error: isAbort ? 'Upstream timeout' : 'Internal Server Error in proxy', details: String(err) },
      { status: isAbort ? 504 : 500 }
    );
  }
}

async function safeText(res) {
  try { return await res.text(); } catch { return ''; }
}
