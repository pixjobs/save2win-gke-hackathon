'use client';
import { useState } from 'react';
import styles from './LoginScreen.module.css';
export default function LoginScreen({ onLogin }) {
  const [token, setToken] = useState('');
  const handleSubmit = (e) => { e.preventDefault(); if (token.trim()) { onLogin(token.trim()); } };
  return (
    <div className={styles.loginContainer}>
      <h1 className={styles.title}>🏆 Welcome to Save2Win</h1>
      <p className={styles.subtitle}>Your AI-Powered Financial Quest</p>
      <div className={styles.instructions}>
        <h3>How to Log In (Demo Mode)</h3>
        <ol>
          <li>Open and log in to the main <strong>Bank of Anthos</strong> app.</li>
          <li>Open browser Dev Tools (F12) → Application → Local Storage.</li>
          <li>Copy the `jwt` value.</li>
          <li>Paste the token below to continue.</li>
        </ol>
      </div>
      <form onSubmit={handleSubmit} className={styles.form}>
        <textarea value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste your JWT token here" className={styles.textarea} rows="4" />
        <button type="submit" className={styles.button}>Enter the Arena</button>
      </form>
    </div>
  );
}