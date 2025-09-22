'use client';

import { useEffect, useState } from 'react';
import styles from './page.module.css';
import LoginScreen from './components/LoginScreen';
import Dashboard from './components/Dashboard';
import LoadingSpinner from './components/LoadingSpinner';

export default function HomePage() {
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState(false);
  const [gameState, setGameState] = useState(null);
  const [error, setError] = useState(null);

  async function checkSession() {
    const res = await fetch('/api/session', { cache: 'no-store' });
    setAuthed(res.ok);
    return res.ok;
  }

  async function loadGameState() {
    setError(null);
    const res = await fetch('/api/game-state', { cache: 'no-store' });
    if (res.ok) {
      setGameState(await res.json());
      return true;
    }
    if (res.status === 401) {
      setError('Connected to Bank of Anthos, but the game engine rejected the token (401).');
      setGameState(null);
      return false;
    }
    setError(`Engine error ${res.status}`);
    setGameState(null);
    return false;
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      const hasSession = await checkSession();   // checks cookie only
      if (hasSession) await loadGameState();     // engine call
      setLoading(false);
    })();

    // Retry on tab focus (covers popup close)
    const onFocus = async () => {
      const hasSession = await checkSession();
      if (hasSession) await loadGameState();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  const handleLogout = async () => {
    try { await fetch('/api/logout', { method: 'POST' }); } catch {}
    window.location.reload();
  };

  if (loading) return <main className={styles.main}><LoadingSpinner /></main>;

  if (!authed) {
    return (
      <main className={styles.main}>
        {error ? <div className={styles.errorCard}><p>{error}</p></div> : null}
        <LoginScreen />
      </main>
    );
  }

  if (error && !gameState) {
    return (
      <main className={styles.main}>
        <div className={styles.errorCard}>
          <p>{error}</p>
          <p style={{fontSize:12,opacity:.8}}>
            Tip: ensure the engine trusts BoA’s JWT public key and you’re forwarding it as <code>Authorization: Bearer …</code>.
          </p>
        </div>
        {/* Optional: still show login to retry if desired */}
        <LoginScreen />
      </main>
    );
  }

  return (
    <main className={styles.main}>
      <Dashboard gameState={gameState} onLogout={handleLogout} />
    </main>
  );
}
