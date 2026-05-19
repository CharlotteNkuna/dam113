Àimport { useSelector, useDispatch } from "react-redux";
import { removeFromCart, clearCart } from "../redux/cartSlice";

export default function Cart() {
  const cartItems = useSelector((state) => state.cart.items);
  const dispatch = useDispatch();

  const total = cartItems
    .reduce((sum, item) => sum + item.price * item.quantity, 0)
    .toFixed(2);

  if (cartItems.length === 0) {
    return (
      <div style={styles.emptyWrap}>
        <h3 style={styles.emptyText}>Your cart is empty üõçÔ∏è</h3>
      </div>
    );
  }

  return (
    <section style={styles.wrap}>
      <h2 style={styles.title}>Your Shopping Cart</h2>
      <div className="row" style={{ rowGap: 16 }}>
        {cartItems.map((item) => (
          <div className="col-md-4" key={item.id}>
            <div style={styles.card}>
              <img
                src={item.image}
                alt={item.title}
                style={styles.image}
              />
              <div style={styles.body}>
                <h5 style={styles.cardTitle}>{item.title}</h5>
                <p style={styles.price}>R{item.price}</p>
                <p style={styles.qty}>Quantity: {item.quantity}</p>
                <button
                  style={styles.remove}
                  onClick={() => dispatch(removeFromCart(item.id))}
                >
                  Remove
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={styles.totalBar}>
        <h4 style={{ margin: 0 }}>Total: R{total}</h4>
        <div>
          <button style={styles.clear} onClick={() => dispatch(clearCart())}>Clear Cart</button>
          <button style={styles.checkout}>Checkout</button>
        </div>
      </div>
    </section>
  );
}

const styles = {
  wrap: {
    padding: '24px',
    color: '#e5e5e5',
  },
  title: {
    textAlign: 'center',
    marginBottom: '16px',
    fontWeight: 700,
  },
  card: {
    background: '#181818',
    borderRadius: '8px',
    overflow: 'hidden',
    boxShadow: '0 6px 20px rgba(0,0,0,0.4)',
    marginBottom: '16px',
  },
  image: {
    width: '100%',
    height: '250px',
    objectFit: 'contain',
    background: '#0f0f0f',
  },
  body: {
    padding: '12px',
  },
  cardTitle: {
    margin: 0,
    marginBottom: '8px',
  },
  price: {
    fontWeight: 700,
    marginBottom: '4px',
  },
  qty: {
    color: '#b3b3b3',
    marginBottom: '12px',
  },
  remove: {
    background: '#333',
    border: '1px solid #444',
    color: '#e5e5e5',
    padding: '8px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    width: '100%',
  },
  totalBar: {
    marginTop: '16px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    background: '#0f0f0f',
    border: '1px solid #222',
    borderRadius: '8px',
    padding: '12px 16px',
  },
  clear: {
    background: 'transparent',
    border: '1px solid #444',
    color: '#e5e5e5',
    padding: '8px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    marginRight: '8px',
  },
  checkout: {
    background: '#e50914',
    border: 'none',
    color: '#fff',
    padding: '8px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontWeight: 700,
  },
  emptyWrap: {
    minHeight: '40vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#e5e5e5',
  },
  emptyText: {
    margin: 0,
  },
};
À*cascade08"(fc989d7b234a986df510f20761272e8831be88ba2Jfile:///Users/dam113/Desktop/React-MiniFlix-movies/src/components/Cart.jsx:2file:///Users/dam113/Desktop/React-MiniFlix-movies