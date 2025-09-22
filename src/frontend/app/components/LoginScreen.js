'use client';

function randState(len = 32) {
  const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  return Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
}

export default function LoginScreen() {
  // Hard-coded for easiest setup (override later with NEXT_PUBLIC_* envs if you want)
  const BOA_ORIGIN   = process.env.NEXT_PUBLIC_BOA_ORIGIN || 'http://35.190.197.221';        // BoA LB (Flask)
  const CLIENT_ID    = process.env.NEXT_PUBLIC_BOA_CLIENT_ID || 'save2win';                  // must match BoA env
  const APP_NAME     = process.env.NEXT_PUBLIC_APP_NAME || 'Save2Win';
  const REDIRECT_URI = process.env.NEXT_PUBLIC_OAUTH_REDIRECT_URI || 'http://34.95.89.70/api/oauth'; // must match BoA env

  const handleLoginClick = () => {
    const state = randState();
    try { sessionStorage.setItem('boa_oauth_state', state); } catch {}

    const url =
      `${BOA_ORIGIN}/login?` +
      `response_type=code` +
      `&client_id=${encodeURIComponent(CLIENT_ID)}` +
      `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
      `&state=${encodeURIComponent(state)}` +
      `&app_name=${encodeURIComponent(APP_NAME)}`;

    const w = window.open(url, '_blank', 'width=800,height=700');
    if (!w) window.location.href = url; else { try { w.opener = null; } catch {} }
  };

  return (
    <div style={{ maxWidth: 480, margin: '64px auto', textAlign: 'center' }}>
      <h1>🏆 Welcome to Save2Win</h1>
      <p>Log in with your Bank of Anthos account to begin.</p>

      <button onClick={handleLoginClick} style={{ padding: '12px 16px', fontWeight: 600, cursor: 'pointer' }}>
        Open Bank of Anthos
      </button>

      <p style={{ marginTop: 12, color: '#666' }}>
        A popup opens for secure sign-in; it closes automatically when done.
      </p>
    </div>
  );
}
