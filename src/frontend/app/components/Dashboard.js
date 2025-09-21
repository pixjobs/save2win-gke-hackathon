import styles from './Dashboard.module.css';
import Card from './Card';
import { Swords, Lightbulb, Medal, LogOut } from 'lucide-react';
export default function Dashboard({ gameState, onLogout }) {
  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <h1>Your Dashboard</h1>
        <div className={styles.playerStats}><span>LEVEL: {gameState.level}</span><span>XP: {gameState.xp}</span></div>
        <button onClick={onLogout} className={styles.logoutButton}><LogOut size={16} /> Logout</button>
      </header>
      <div className={styles.grid}>
        <Card title="Current Quest" icon={<Swords color="var(--quest-accent)" />}><p>{gameState.quest}</p></Card>
        <Card title="AI Financial Tip" icon={<Lightbulb color="var(--tip-accent)" />}><p>{gameState.tip}</p></Card>
        <div className={styles.fullWidthCard}>
          <Card title="Achievement Badges" icon={<Medal color="var(--accent-color)" />}>
            {gameState.badges.length > 0 ? ( <div className={styles.badgeContainer}> {gameState.badges.map(b => <span key={b.id} className={styles.badge}>{b.title}</span>)} </div> ) : <p>Complete quests to earn your first badge!</p>}
          </Card>
        </div>
      </div>
    </div>
  );
}