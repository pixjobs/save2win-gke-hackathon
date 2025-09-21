import { NextResponse } from 'next/server';
const ENGINE_URL = 'http://save2win-engine.boa.svc.cluster.local/api/v1/game-state';
export async function GET(request) {
  try {
    const authHeader = request.headers.get('Authorization');
    if (!authHeader) { return NextResponse.json({ error: 'Authorization header is missing' }, { status: 401 }); }
    const response = await fetch(ENGINE_URL, { headers: { 'Authorization': authHeader }, cache: 'no-store' });
    if (!response.ok) {
      const errorData = await response.text();
      return NextResponse.json({ error: 'Failed to fetch game state from engine', details: errorData }, { status: response.status });
    }
    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('Error in API proxy route:', error);
    return NextResponse.json({ error: 'Internal Server Error in proxy' }, { status: 500 });
  }
}