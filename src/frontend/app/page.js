'use client';
import { useState, useEffect } from 'react';
import styles from './page.module.css';
import LoginScreen from './components/LoginScreen';
import Dashboard from './components/Dashboard';
import LoadingSpinner from './components/LoadingSpinner';

export default function HomePage() {
  const [jwt, setJwt] = useState(null);
  const [gameState, setGameState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const storedJwt = localStorage.getItem('s2w_jwt');
    if (storedJwt) { setJwt(storedJwt); }
  }, []);

  useEffect(() => {
    if (!jwt) { setGameState(null); return; }
    const fetchGameState = async () => {
      setLoading(true); setError(null);
      try {
        const response = await fetch('/api/game-state', { headers: { 'Authorization': `Bearer ${jwt}` } });
        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(`Failed to load data: ${response.status}. ${errorBody}`);
        }
        setGameState(await response.json());
      } catch (e) { setError(e.message); } finally { setLoading(false); }
    };
    fetchGameState();
  }, [jwt]);

  const handleLogin = (token) => { localStorage.setItem('s2w_jwt', token); setJwt(token); };
  const handleLogout = () => { localStorage.removeItem('s2w_jwt'); setJwt(null); };
  const renderContent = () => {
    if (loading) return <LoadingSpinner />;
    if (error) return <div className={styles.errorCard}><p>Error: {error}</p><p>Please check your JWT or try again.</p></div>;
    if (gameState) return <Dashboard gameState={gameState} onLogout={handleLogout} />;
    return null;
  };
  return ( <main className={styles.main}> {!jwt ? <LoginScreen onLogin={handleLogin} /> : renderContent()} </main> );
}