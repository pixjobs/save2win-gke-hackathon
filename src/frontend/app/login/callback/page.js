'use client';
import { useEffect } from 'react';

export default function Callback() {
  useEffect(() => {
    // The main page (window.opener) has an 'onFocus' event listener
    // that will automatically check the session and load the game state.
    // Forcing a reload here creates a race condition and is no longer necessary.

    // We just need to close the popup, which will trigger the 'onFocus'
    // event on the main page.
    window.close();
  }, []); // The empty dependency array ensures this runs only once

  // It's good practice to show the user a message while the script runs.
  return <p style={{padding:24, fontFamily:'system-ui'}}>Finishing sign-in…</p>;
}