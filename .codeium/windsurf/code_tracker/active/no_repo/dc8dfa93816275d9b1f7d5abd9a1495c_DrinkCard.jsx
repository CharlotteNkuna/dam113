œimport { useDispatch } from 'react-redux'
import { openDetails } from '../features/drinks/drinksSlice'

export default function DrinkCard({ drink }) {
  const dispatch = useDispatch()

  return (
    <div className="drink-card">
      <img src={drink.thumb} alt={drink.name} onClick={() => dispatch(openDetails(drink))} />
      <div className="drink-info">
        <h3>{drink.name}</h3>
        <p className="meta">
          <span>{drink.category}</span> ‚Ä¢ <span>{drink.alcoholic}</span> ‚Ä¢ <span>{drink.glass}</span>
        </p>
        <div className="row">
          <button className="btn btn-outline" onClick={() => dispatch(openDetails(drink))}>Details</button>
        </div>
      </div>
    </div>
  )
}
h *cascade08hô *cascade08ôª *cascade08ªë *cascade08ëæ*cascade08æ† *cascade08†¥ *cascade08¥¥*cascade08¥µ *cascade08µ¡ *cascade08¡«*cascade08«” *cascade08”’*cascade08’÷ *cascade08÷ÿ*cascade08ÿŸ *cascade08Ÿ‹*cascade08‹ﬁ *cascade08ﬁﬂ*cascade08ﬂ‡ *cascade08‡‰*cascade08‰Ê *cascade08Êı*cascade08ıˆ *cascade08ˆà*cascade08àç *cascade08çï*cascade08ïñ *cascade08ñó*cascade08óò *cascade08òõ*cascade08õù *cascade08ùû*cascade08û™ *cascade08™∞*cascade08∞œ *cascade082Cfile:///Users/dam113/Desktop/liquorose/src/components/DrinkCard.jsx