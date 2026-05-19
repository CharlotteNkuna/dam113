èexport default function DetailsModal({ drink, onClose }) {
  return (
    <div className="modal" role="dialog" aria-modal="true">
      <div className="modal-content">
        <button className="modal-close" onClick={onClose} aria-label="Close">√ó</button>
        <div className="modal-body">
          <img src={drink.thumb} alt={drink.name} />
          <div>
            <h2>{drink.name}</h2>
            <p className="meta"><span>{drink.category}</span> ‚Ä¢ <span>{drink.alcoholic}</span> ‚Ä¢ <span>{drink.glass}</span></p>
            {drink.instructions && <p>{drink.instructions}</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
è*cascade082Ffile:///Users/dam113/Desktop/liquorose/src/components/DetailsModal.jsx