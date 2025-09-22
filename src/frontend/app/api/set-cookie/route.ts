// NEW FILE: app/api/set-cookie/route.js

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
    'SameSite=Lax', // Lax is fine here because it's a same-site context
    `Max-Age=${maxAge}`,
  ];
  return parts.join('; ');
}

export function GET(req) {
  const url = new URL(req.url);
  const idToken = url.searchParams.get('id_token');
  const state = url.searchParams.get('state') || '';
  const origin = getOrigin(req);

  if (!idToken) {
    return new Response('Missing token', { status: 400 });
  }

  const cookie = setCookieHeader(idToken);

  // Now perform the final redirect to the login callback page
  const finalRedirectUrl = `${origin}/login/callback?state=${encodeURIComponent(state)}`;

  return new Response(null, {
    status: 302,
    headers: {
      Location: finalRedirectUrl,
      'Set-Cookie': cookie,
    },
  });
}