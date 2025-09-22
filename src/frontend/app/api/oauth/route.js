// app/api/oauth/route.js
export const dynamic = 'force-dynamic';

function getOrigin(req) {
  const proto = req.headers.get('x-forwarded-proto') || 'http';
  const host  = req.headers.get('x-forwarded-host') || req.headers.get('host');
  return `${proto}://${host}`;
}

function setCookieHeader(idToken) {
  const maxAge = 60 * 60 * 8; // 8 hours
  const parts = [
    `boa_id_token=${encodeURIComponent(idToken)}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    `Max-Age=${maxAge}`,
    // 'Secure', // enable once you're on HTTPS
  ];
  return parts.join('; ');
}

function redirect(to, cookie) {
  return new Response(null, {
    status: 302,
    headers: cookie
      ? { Location: to, 'Set-Cookie': cookie }
      : { Location: to },
  });
}

export async function POST(req) {
  // BoA posts x-www-form-urlencoded with: state, id_token
  const form = await req.formData();
  const state = form.get('state') || '';
  const idToken = form.get('id_token') || form.get('code') || '';

  if (!idToken) {
    // BoA will treat non-302 as error; still 302 home
    const origin = getOrigin(req);
    return redirect(`${origin}/`, null);
  }

  const origin = getOrigin(req);
  const cookie = setCookieHeader(idToken);
  // 302 so BoA is happy; your /login/callback can close the popup & reload opener
  return redirect(`${origin}/login/callback?state=${encodeURIComponent(state)}`, cookie);
}

// Tolerant GET handler to avoid 405s and support query-style callbacks if they occur
export function GET(req) {
  const url = new URL(req.url);
  const state = url.searchParams.get('state') || '';
  const idToken = url.searchParams.get('id_token') || url.searchParams.get('code') || '';
  const origin = getOrigin(req);

  if (idToken) {
    const cookie = setCookieHeader(idToken);
    return redirect(`${origin}/login/callback?state=${encodeURIComponent(state)}`, cookie);
  }
  return redirect(`${origin}/`, null);
}
