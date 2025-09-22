// FILE: app/api/game-state/route.js
// This is the single, correct API route that the Dashboard component will call.

export const dynamic = 'force-dynamic';

import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import http from 'node:http';
import https from 'node:https';

// --- START OF FIX ---
// The ENGINE_URL now correctly points to the /summary endpoint on the backend.
const BASE_URL =
  process.env.ENGINE_URL ||
  'http://save2win-engine.boa.svc.cluster.local/api/v1/game-state';

const ENGINE_URL = `${BASE_URL.replace(/\/+$/, '')}/summary`;
// --- END OF FIX ---


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
  const to = setTimeout(() => controller.abort(), 15_000);

  try {
    const resp = await fetch(ENGINE_URL, { // It now calls the correct summary URL
      headers: { authorization: authHeader },
      cache: 'no-store',
      // @ts-ignore — Node runtime
      agent,
      signal: controller.signal,
    });

    clearTimeout(to);

    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      return NextResponse.json(
        { error: 'Failed to fetch game state from engine', status: resp.status, details: text || undefined },
        { status: resp.status }
      );
    }

    const data = await resp.json();
    
    // --- RECOMMENDED RESHAPE ---
    // Reshape the data to match what the Dashboard component expects.
    const reshapedData = {
      ...data.game, // Unpack xp, level, badges, quest, tip
      transactions: data.summary?.recent || [],
      buckets: data.summary?.buckets || [],
      weeklySummary: data.summary?.stats?.last_7d || {},
      engine: data.version, // Pass through version info if available
    };
    return NextResponse.json(reshapedData);
    // --- END RESHAPE ---

  } catch (err) {
    clearTimeout(to);
    const isAbort = err?.name === 'AbortError';
    return NextResponse.json(
      { error: isAbort ? 'Upstream timeout' : 'Internal Server Error in proxy', details: String(err) },
      { status: isAbort ? 504 : 500 }
    );
  }
}