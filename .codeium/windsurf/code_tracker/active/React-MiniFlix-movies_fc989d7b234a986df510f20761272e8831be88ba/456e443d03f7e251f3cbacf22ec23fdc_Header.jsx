°import React from 'react';
import { Link } from 'react-router-dom';
import { useSelector } from 'react-redux';

export default function Header({ onLogout }) {
  // Use optional chaining and default to empty array
  const cartItems = useSelector((state) => state.cart?.items || []);
  const currentUser = useSelector((state) => state.user?.currentUser);

  return (
    <header style={styles.header}>
      <div style={styles.left}>
        <div style={styles.brand}>MiniFlix</div>
      </div>
      <nav style={styles.nav}>
        <Link to="/dashboard" style={styles.navLink}>Home</Link>
        <Link to="/cart" style={styles.navLink}>Cart ({cartItems.length})</Link>
        {currentUser && (
          <>
            <span style={styles.user}>Hi, {currentUser.email}</span>
            <button onClick={onLogout} style={styles.logout}>Logout</button>
          </>
        )}
      </nav>
    </header>
  );
}

const styles = {
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 24px',
    background: '#0f0f0f',
    color: '#fff',
    borderBottom: '1px solid #222',
    position: 'sticky',
    top: 0,
    zIndex: 10,
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  brand: {
    fontSize: '24px',
    fontWeight: 800,
    color: '#e50914',
    letterSpacing: '0.5px',
  },
  nav: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  navLink: {
    color: '#e5e5e5',
    textDecoration: 'none',
    padding: '6px 8px',
    borderRadius: '4px',
  },
  user: {
    color: '#b3b3b3',
    marginRight: '6px',
    fontSize: '14px',
  },
  logout: {
    background: '#e50914',
    border: 'none',
    color: '#fff',
    padding: '8px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontWeight: 700,
  },
};
°*cascade08"(fc989d7b234a986df510f20761272e8831be88ba2Lfile:///Users/dam113/Desktop/React-MiniFlix-movies/src/components/Header.jsx:2file:///Users/dam113/Desktop/React-MiniFlix-movies