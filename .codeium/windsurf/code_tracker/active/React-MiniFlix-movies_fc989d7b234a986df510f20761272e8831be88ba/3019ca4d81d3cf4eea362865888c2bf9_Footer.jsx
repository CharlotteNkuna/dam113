„import React from 'react';

export default function Footer() {
  return (
    <footer style={styles.footer}>
      <p>&copy; {new Date().getFullYear()} MyNetflix. All rights reserved.</p>
      <div>
        <a style={styles.link} href="#privacy">Privacy Policy</a> | 
        <a style={styles.link} href="#terms">Terms of Service</a> | 
        <a style={styles.link} href="#contact">Contact Us</a>
      </div>
    </footer>
  );
}

const styles = {
  footer: {
    marginTop: '50px',
    padding: '24px',
    textAlign: 'center',
    backgroundColor: '#0f0f0f',
    color: '#b3b3b3',
    borderTop: '1px solid #222',
    position: 'relative',
    bottom: 0,
    width: '100%',
  },
  link: {
    color: '#b3b3b3',
    margin: '0 6px',
    textDecoration: 'none'
  }
};
„*cascade08"(fc989d7b234a986df510f20761272e8831be88ba2Lfile:///Users/dam113/Desktop/React-MiniFlix-movies/src/components/Footer.jsx:2file:///Users/dam113/Desktop/React-MiniFlix-movies