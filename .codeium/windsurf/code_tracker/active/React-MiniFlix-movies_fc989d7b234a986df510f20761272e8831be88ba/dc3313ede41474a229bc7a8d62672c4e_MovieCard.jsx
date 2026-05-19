†import { useDispatch } from 'react-redux';
import { addToCart } from '../redux/cartSlice';

export default function MovieCard({ movie }) {
  const dispatch = useDispatch();
  const imageUrl = movie.poster_path
    ? `https://image.tmdb.org/t/p/w500${movie.poster_path}`
    : 'https://via.placeholder.com/500x750?text=No+Image';

  const price = (Math.random() * 100 + 50).toFixed(2);

  const handleAdd = () => {
    dispatch(
      addToCart({
        id: movie.id,
        title: movie.title,
        price: Number(price),
        image: imageUrl,
      })
    );
  };

  return (
    <div style={styles.card}>
      <div style={styles.imageWrap}>
        <img src={imageUrl} alt={movie.title} style={styles.image} />
      </div>
      <div style={styles.body}>
        <h5 style={styles.title}>{movie.title}</h5>
        <div style={styles.meta}>
          <span style={styles.price}>R{price}</span>
          <button style={styles.button} onClick={handleAdd}>Add to Cart</button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  card: {
    background: '#181818',
    borderRadius: '8px',
    overflow: 'hidden',
    boxShadow: '0 6px 20px rgba(0,0,0,0.4)',
    transition: 'transform .2s ease, box-shadow .2s ease',
  },
  imageWrap: {
    width: '100%',
    aspectRatio: '2/3',
    background: '#111',
  },
  image: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    display: 'block',
  },
  body: {
    padding: '12px',
  },
  title: {
    margin: 0,
    marginBottom: '8px',
    fontSize: '16px',
    color: '#fff',
  },
  meta: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  price: {
    color: '#e5e5e5',
    fontWeight: 600,
  },
  button: {
    background: '#e50914',
    border: 'none',
    color: '#fff',
    padding: '8px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: '14px',
  },
};
\*cascade08\Š *cascade08Š¬*cascade08¬‚ *cascade08‚½*cascade08½¯ *cascade08¯Ã*cascade08Ã† *cascade08"(fc989d7b234a986df510f20761272e8831be88ba2Ofile:///Users/dam113/Desktop/React-MiniFlix-movies/src/components/MovieCard.jsx:2file:///Users/dam113/Desktop/React-MiniFlix-movies