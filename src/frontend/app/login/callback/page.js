'use client';
import { useEffect } from 'react';

export default function Callback() {
  useEffect(() => {
    try {
      if (window.opener && !window.opener.closed) window.opener.location.reload();
    } catch {}
    window.close();
  }, []);
  return <p style={{padding:24,fontFamily:'system-ui'}}>Finishing sign-in…</p>;
}
