// Patched app/api/oauth/route.js

export const dynamic = 'force-dynamic';

function getOrigin(req) {
  const proto = req.headers.get('x-forwarded-proto') || 'http';
  const host  = req.headers.get('x-forwarded-host') || req.headers.get('host');
  return `${proto}://${host}`;
}

function redirect(to) {
  return new Response(null, {
    status: 302,
    headers: { Location: to },
  });
}

// This function now just redirects to our cookie-setting endpoint
async function handleRequest(req) {
  let idToken = '';
  let state = '';
  const origin = getOrigin(req);
  
  if (req.method === 'POST') {
    const form = await req.formData();
    state = form.get('state') || '';
    idToken = form.get('id_token') || form.get('code') || '';
  } else { // GET
    const url = new URL(req.url);
    state = url.searchParams.get('state') || '';
    idToken = url.searchParams.get('id_token') || url.searchParams.get('code') || '';
  }

  if (!idToken) {
    // Redirect home on failure
    return redirect(`${origin}/`);
  }

  // Redirect to a NEW endpoint on our own site with the token and state
  const redirectTo = new URL(`${origin}/api/set-cookie`);
  redirectTo.searchParams.set('id_token', idToken);
  redirectTo.searchParams.set('state', state);

  return redirect(redirectTo.toString());
}

export const POST = handleRequest;
export const GET = handleRequest;