export const dynamic = 'force-dynamic';

import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import http from 'node:http';
import https from 'node:https';

const BASE =
  process.env.ENGINE_URL ||
  'http://save2win-engine.boa.svc.cluster.local/api/v1/game-state';

const ENGINE_URL = `${BASE.replace(/\/+$/, '')}/summary`;

const agent = ENGINE_URL.startsWith('https:')
  ? new https.Agent({ keepAlive: true, timeout: 30_000 })
  : new http.Agent({ keepAlive: true, timeout: 30_000 });

function authHeaderFrom(req) {
  const token = cookies().get('boa_id_token')?.value;
  const headerAuth = req.headers.get('authorization');
  return token ? `Bearer ${token}` : headerAuth;
}

async function safeText(res) {
  try { return await res.text(); } catch { return ''; }
}

function joinUrlWithSearch(base, searchParams) {
  if (!searchParams || ![...searchParams].length) return base;
  const sep = base.includes('?') ? '&' : '?';
  return `${base}${sep}${searchParams.toString()}`;
}

export async function GET(req) {
  const authHeader = authHeaderFrom(req);
  if (!authHeader) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  const url = joinUrlWithSearch(ENGINE_URL, new URL(req.url).searchParams);
  const controller = new AbortController();
  const to = setTimeout(() => controller.abort(), 15_000);

  try {
    const resp = await fetch(url, {
      headers: { authorization: authHeader },
      cache: 'no-store',
      // @ts-ignore – Node runtime
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
        { error: 'Failed to fetch engine summary', status: resp.status, details: text || undefined },
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
