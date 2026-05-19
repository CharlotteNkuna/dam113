Çimport React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Footer from '../components/Footer';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();

  const handleRegister = () => {
    const users = JSON.parse(localStorage.getItem('users')) || [];

    const existingUser = users.find(u => u.email === email);
    if (existingUser) {
      alert('User already exists. Please login.');
      navigate('/login');
      return;
    }

    users.push({ email, password });
    localStorage.setItem('users', JSON.stringify(users));
    alert('Registration successful! Please login.');
    navigate('/login');
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div style={styles.brand}>MiniFlix</div>
      </header>

      <main style={styles.main}>
        <div style={styles.card}>
          <h2 style={styles.title}>Create your account</h2>
          <div style={styles.form}> 
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={styles.input}
            />
            <button onClick={handleRegister} style={styles.button}>Get Started</button>
            <p style={styles.helperText}>
              Already have an account?{' '}
              <Link to="/login" style={styles.link}>Sign in</Link>
            </p>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}

const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'radial-gradient(50% 120% at 50% 50%, #141414 0%, #000 100%)',
    color: '#fff',
  },
  header: {
    padding: '24px 32px',
  },
  brand: {
    fontSize: '28px',
    fontWeight: 800,
    color: '#e50914',
    letterSpacing: '0.5px',
  },
  main: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '32px 16px',
  },
  card: {
    width: '100%',
    maxWidth: '420px',
    background: 'rgba(0,0,0,0.75)',
    borderRadius: '8px',
    padding: '40px 36px',
    boxShadow: '0 10px 30px rgba(0,0,0,0.6)',
  },
  title: {
    margin: 0,
    marginBottom: '24px',
    fontSize: '26px',
    fontWeight: 700,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
  },
  input: {
    padding: '14px 16px',
    background: '#333',
    border: '1px solid #444',
    color: '#fff',
    borderRadius: '4px',
    outline: 'none',
    fontSize: '14px',
  },
  button: {
    marginTop: '8px',
    padding: '12px 16px',
    background: '#e50914',
    border: 'none',
    color: '#fff',
    borderRadius: '4px',
    fontWeight: 700,
    cursor: 'pointer',
    fontSize: '16px',
  },
  helperText: {
    marginTop: '10px',
    color: '#b3b3b3',
    fontSize: '14px',
  },
  link: {
    color: '#fff',
    textDecoration: 'none',
  },
};
Ç*cascade08"(fc989d7b234a986df510f20761272e8831be88ba2Ifile:///Users/dam113/Desktop/React-MiniFlix-movies/src/pages/Register.jsx:2file:///Users/dam113/Desktop/React-MiniFlix-movies