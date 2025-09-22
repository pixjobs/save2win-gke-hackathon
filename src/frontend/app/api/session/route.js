// NEW or VERIFY this file: app/api/session/route.js

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export function GET(req) {
  // On the server-side, we can securely access HttpOnly cookies.
  const token = cookies().get('boa_id_token')?.value;

  if (token) {
    // The cookie exists, so the user has a session.
    // We could optionally decode the JWT here to check for expiration,
    // but for now, just checking existence is sufficient.
    return NextResponse.json({ authenticated: true }, { status: 200 });
  } else {
    // No cookie was found, so the user is not authenticated.
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }
}