import styles from './Card.module.css';
export default function Card({ title, icon, children }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>{icon}<h2 className={styles.cardTitle}>{title}</h2></div>
      <div className={styles.cardContent}>{children}</div>
    </div>
  );
}