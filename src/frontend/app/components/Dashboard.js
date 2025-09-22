'use client';

import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_GAME_STATE_API || '/api/game-state';

/* ----------------------------- small view helpers ---------------------------- */

const fmtCurrency = (n) =>
  Number.isFinite(Number(n))
    ? Number(n).toLocaleString(undefined, { style: 'currency', currency: 'USD' })
    : n ?? '—';

const Card = ({ title, children, right }) => (
  <div style={cardStyle}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      {title && <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 16 }}>{title}</div>}
      {right}
    </div>
    {children}
  </div>
);

const cardStyle = {
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 16,
  boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.02)',
  background: '#fff'
};

const thStyle = { padding: '10px 8px', fontWeight: 600, fontSize: 13, color: '#374151' };
const tdStyle = { padding: '10px 8px', fontSize: 14, color: '#111827', verticalAlign: 'top' };
const pillStyle = {
  display: 'inline-block',
  background: '#eef2ff',
  borderRadius: 999,
  padding: '4px 10px',
  fontSize: 13,
  fontWeight: 500,
  color: '#3730a3'
};

function Progress({ value = 0, label = '' }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div aria-label={label} title={label} style={{ width: '100%' }}>
      <div style={{
        height: 8, width: '100%', background: '#f3f4f6', borderRadius: 999, overflow: 'hidden'
      }}>
        <div style={{ width: `${v}%`, height: '100%', background: '#6366f1' }} />
      </div>
      <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>{v}%</div>
    </div>
  );
}

function Kpi({ label, value, sub }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ color: '#6b7280' }}>{label}</span>
        <strong>{value}</strong>
      </div>
      {sub ? <div style={{ color: '#9ca3af', fontSize: 12, marginTop: 2 }}>{sub}</div> : null}
    </div>
  );
}

function btnStyle(disabled) {
  return {
    borderRadius: 999,
    padding: '8px 14px',
    border: '1px solid #d1d5db',
    background: disabled ? '#f9fafb' : '#fff',
    color: '#111827',
    cursor: disabled ? 'not-allowed' : 'pointer'
  };
}

function btnPrimaryStyle(disabled) {
  return {
    borderRadius: 999,
    padding: '8px 14px',
    border: '1px solid transparent',
    background: disabled ? '#c7d2fe' : '#6366f1',
    color: '#fff',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontWeight: 600
  };
}

/* ------------------------- light client-side intelligence ------------------------- */

/** derive buckets if engine didn’t send them */
function deriveBuckets(transactions = []) {
  const byCat = new Map();
  transactions.forEach((t) => {
    const amt = Number(t.amount);
    if (!Number.isFinite(amt)) return;
    if (amt <= 0) {
      const cat = (t.category || guessCategory(t) || 'Other').trim();
      byCat.set(cat, (byCat.get(cat) || 0) + Math.abs(amt));
    }
  });
  return [...byCat.entries()]
    .map(([category, total]) => ({ category, total }))
    .sort((a, b) => b.total - a.total);
}

function guessCategory(t) {
  const m = (t.merchant || t.description || '').toLowerCase();
  if (/coffee|cafe|starbucks|dunkin/.test(m)) return 'Coffee';
  if (/uber|lyft|transport|metro|bus|train|fuel|gas/.test(m)) return 'Transport';
  if (/grocery|market|supermarket|whole foods|kroger|aldi|tesco|safeway/.test(m)) return 'Groceries';
  if (/netflix|spotify|prime|apple tv|disney/.test(m)) return 'Subscriptions';
  if (/restaurant|diner|grill|bar|pizza|sushi|taco|burger/.test(m)) return 'Dining';
  return 'Other';
}

/** derive weekly summary if engine didn’t send it */
function deriveWeekly(transactions = []) {
  let income = 0, spending = 0;
  const weekCutoff = Date.now() - 7 * 24 * 3600 * 1000;
  transactions.forEach((t) => {
    const ts = new Date(t.date || t.timestamp || Date.now()).getTime();
    if (!Number.isFinite(ts) || ts < weekCutoff) return;
    const amt = Number(t.amount);
    if (!Number.isFinite(amt)) return;
    if (amt > 0) income += amt; else spending += Math.abs(amt);
  });
  return { income, spending, net: income - spending };
}

/** pick top merchants for a small leaderboard */
function topMerchants(transactions = [], limit = 5) {
  const map = new Map();
  transactions.forEach((t) => {
    const amt = Number(t.amount);
    if (!Number.isFinite(amt) || amt >= 0) return;
    const name = (t.merchant || t.description || 'Unknown').trim();
    map.set(name, (map.get(name) || 0) + Math.abs(amt));
  });
  return [...map.entries()]
    .map(([merchant, total]) => ({ merchant, total }))
    .sort((a, b) => b.total - a.total)
    .slice(0, limit);
}

function barPercent(total, buckets) {
  const sum = buckets.reduce((acc, b) => acc + (Number(b.total) || 0), 0);
  if (!sum) return 0;
  const t = Number(total) || 0;
  return Math.max(0, Math.min(100, (t / sum) * 100));
}

/* --------------------------------- component -------------------------------- */

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [fetching, setFetching] = useState(false);
  const [err, setErr] = useState(null);

  const query = useMemo(() => {
    const sp = new URLSearchParams();
    // ask engine for everything it can provide; we’ll gracefully handle missing pieces
    sp.set('include', 'transactions,weeklySummary,buckets,achievements,summary');
    return sp.toString();
  }, []);

  async function load() {
    setFetching(true);
    setErr(null);
    try {
      const resp = await fetch(`${API_BASE}?${query}`, { cache: 'no-store' });
      if (!resp.ok) {
        const details = await resp.text().catch(() => '');
        throw new Error(`Engine error ${resp.status}: ${details || resp.statusText}`);
      }
      const json = await resp.json();
      setData(json);
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setFetching(false);
    }
  }

  async function refreshCoaching() {
    setFetching(true);
    setErr(null);
    try {
      const resp = await fetch(`${API_BASE}?${query}`, { method: 'POST' });
      if (!resp.ok) {
        const details = await resp.text().catch(() => '');
        throw new Error(`Engine POST error ${resp.status}: ${details || resp.statusText}`);
      }
      await load();
    } catch (e) {
      setErr(e.message || String(e));
      setFetching(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const xp = data?.xp ?? 0;
  const level = data?.level ?? 1;
  const quest = data?.quest || 'No quest available yet.';
  const tip = data?.tip || 'Small steps add up—try a homemade coffee this week.';
  const badges = Array.isArray(data?.badges) ? data.badges : (data?.achievements || []);
  const transactions = Array.isArray(data?.transactions) ? data.transactions : [];
  const buckets = Array.isArray(data?.buckets) && data.buckets.length ? data.buckets : deriveBuckets(transactions);
  const weekly = data?.weeklySummary && (data.weeklySummary.income != null)
    ? data.weeklySummary
    : deriveWeekly(transactions);
  const merchants = topMerchants(transactions, 5);

  // a tiny “savings” nudge based on coffee/dining spend this week
  const coffeeSpend = buckets.find(b => (b.category || '').toLowerCase() === 'coffee')?.total || 0;
  const diningSpend = buckets.find(b => (b.category || '').toLowerCase() === 'dining')?.total || 0;
  const potentialSave = Math.round((coffeeSpend * 0.4 + diningSpend * 0.2) * 100) / 100;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* Header / actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <h2 style={{ margin: 0 }}>Save2Win — Your Personal Finance Quest</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={load} disabled={fetching} style={btnStyle(fetching)} aria-label="Refresh" title="Refresh">
            ⟳ Refresh
          </button>
          <button
            onClick={refreshCoaching}
            disabled={fetching}
            style={btnPrimaryStyle(fetching)}
            aria-label="New coaching"
            title="Ask AI for a fresh quest & tip"
          >
            ✨ New Coaching
          </button>
        </div>
      </div>

      {err && (
        <Card>
          <div style={{ color: '#b91c1c', fontWeight: 700, marginBottom: 6 }}>Error</div>
          <code style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{err}</code>
        </Card>
      )}

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        <Card title="Level">
          {fetching && !data ? <Skeleton height={36} /> : <div style={{ fontSize: 28, fontWeight: 700 }}>{level}</div>}
          <div style={{ color: '#6b7280' }}>Your current tier</div>
        </Card>

        <Card title="XP">
          {fetching && !data ? <Skeleton height={36} /> : <div style={{ fontSize: 28, fontWeight: 700 }}>{xp}</div>}
          <div style={{ color: '#6b7280' }}>Total experience</div>
          <div style={{ marginTop: 8 }}>
            <Progress value={Math.min((xp % 1000) / 10, 100)} label="Level progress" />
          </div>
        </Card>

        <Card title="This Week">
          {fetching && !data ? (
            <div style={{ display: 'grid', gap: 6 }}>
              <Skeleton height={16} /><Skeleton height={16} /><Skeleton height={16} />
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 6 }}>
              <Kpi label="Income" value={fmtCurrency(weekly?.income ?? 0)} />
              <Kpi label="Spending" value={fmtCurrency(weekly?.spending ?? 0)} />
              <Kpi label="Net" value={fmtCurrency(weekly?.net ?? 0)} />
            </div>
          )}
        </Card>
      </div>

      {/* Quest & Tip */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <Card title="Your Quest" right={<span style={{ color: '#9ca3af', fontSize: 12 }}>1 week</span>}>
          {fetching && !data ? <Skeleton lines={3} /> : <div style={{ fontSize: 16, lineHeight: 1.5 }}>{quest}</div>}
          <ul style={{ marginTop: 12, marginBottom: 0, color: '#6b7280', fontSize: 14 }}>
            <li>Finish within 7 days to earn bonus XP.</li>
            <li>Proof is based on your real transactions (no manual steps).</li>
          </ul>
        </Card>

        <Card title="Coach’s Tip">
          {fetching && !data ? <Skeleton lines={2} /> : <div style={{ fontSize: 16, lineHeight: 1.5 }}>{tip}</div>}
          <div style={{ marginTop: 10, fontSize: 13, color: '#6b7280' }}>
            Potential save this week (coffee/dining tweaks): <strong>{fmtCurrency(potentialSave)}</strong>
          </div>
        </Card>
      </div>

      {/* Achievements */}
      <Card title="Achievements">
        {fetching && !data ? (
          <div style={{ display: 'flex', gap: 8 }}><Skeleton width={90} height={28} /><Skeleton width={110} height={28} /></div>
        ) : badges?.length ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {badges.map((b, i) => (
              <span key={b.id || i} style={pillStyle}>🏅 {b.title || b.name || b.id}</span>
            ))}
          </div>
        ) : (
          <div style={{ color: '#6b7280' }}>Complete quests to unlock badges.</div>
        )}
      </Card>

      {/* Buckets & Top Merchants */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Card title="Spending Buckets">
          {fetching && !data ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <Skeleton height={16} /><Skeleton height={16} /><Skeleton height={16} />
            </div>
          ) : buckets?.length ? (
            <div style={{ display: 'grid', gap: 8 }}>
              {buckets.map((b, i) => (
                <div key={b.category || i} style={{ display: 'grid', gap: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong>{b.category || 'Other'}</strong>
                    <span>{fmtCurrency(b.total || 0)}</span>
                  </div>
                  <Progress value={barPercent(b.total, buckets)} />
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#6b7280' }}>No categorized spending yet.</div>
          )}
        </Card>

        <Card title="Top Merchants (7d)">
          {fetching && !data ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <Skeleton height={16} /><Skeleton height={16} /><Skeleton height={16} />
            </div>
          ) : merchants?.length ? (
            <div style={{ display: 'grid', gap: 8 }}>
              {merchants.map((m, i) => (
                <div key={m.merchant || i} style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{i + 1}. {m.merchant}</span>
                  <strong>{fmtCurrency(m.total)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#6b7280' }}>We’ll show your top spenders here.</div>
          )}
        </Card>
      </div>

      {/* Recent Transactions */}
      <Card title="Recent Transactions">
        {fetching && !data ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <Skeleton height={18} /><Skeleton height={18} /><Skeleton height={18} />
          </div>
        ) : transactions?.length ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: '1px solid #e5e7eb' }}>
                  <th style={thStyle}>Date</th>
                  <th style={thStyle}>Type</th>
                  <th style={thStyle}>Account</th>
                  <th style={thStyle}>Merchant / Label</th>
                  <th style={thStyle}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {transactions.slice(0, 12).map((t, i) => {
                  const amt = Number(t.amount);
                  const isCredit = Number.isFinite(amt) ? amt > 0 : (t.type || '').toLowerCase() === 'credit';
                  return (
                    <tr key={t.id || i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={tdStyle}>{t.date || t.timestamp || ''}</td>
                      <td style={tdStyle}>{t.type || (isCredit ? 'Credit' : 'Debit')}</td>
                      <td style={tdStyle}>{t.accountNum || t.account || t.account_id || ''}</td>
                      <td style={tdStyle}>{t.merchant || t.description || t.label || '—'}</td>
                      <td style={{ ...tdStyle, fontWeight: 600, color: isCredit ? '#059669' : '#b91c1c' }}>
                        {fmtCurrency(amt)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {transactions.length > 12 && (
              <div style={{ marginTop: 8, color: '#6b7280', fontSize: 14 }}>
                Showing 12 of {transactions.length}. (View more in Bank of Anthos.)
              </div>
            )}
          </div>
        ) : (
          <div style={{ color: '#6b7280' }}>No recent transactions available.</div>
        )}
      </Card>

      {/* Footer / status */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', color: '#6b7280', fontSize: 13 }}>
        <span>Status: {fetching ? 'Loading…' : 'Ready'}</span>
        {data?.engine && <span>• Engine: {data.engine}</span>}
        {data?.fingerprint && <span>• Key fp: {String(data.fingerprint).slice(0, 10)}…</span>}
      </div>
    </div>
  );
}

/* --------------------------------- skeleton -------------------------------- */

function Skeleton({ width = '100%', height = 14, lines = 1 }) {
  if (lines > 1) {
    return (
      <div style={{ display: 'grid', gap: 6 }}>
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} style={{
            width: '100%', height,
            background: 'linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 37%, #f3f4f6 63%)',
            backgroundSize: '400% 100%',
            borderRadius: 6,
            animation: 'shimmer 1.4s ease-in-out infinite'
          }} />
        ))}
        <style>{`@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}`}</style>
      </div>
    );
  }
  return (
    <div style={{
      width, height,
      background: 'linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 37%, #f3f4f6 63%)',
      backgroundSize: '400% 100%',
      borderRadius: 6,
      animation: 'shimmer 1.4s ease-in-out infinite'
    }} />
  );
}
