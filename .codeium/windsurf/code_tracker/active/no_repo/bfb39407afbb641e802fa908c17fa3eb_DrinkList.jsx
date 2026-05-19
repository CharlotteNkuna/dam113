Õimport { useDispatch, useSelector } from 'react-redux'
import DrinkCard from './DrinkCard'
import DetailsModal from './DetailsModal'
import { closeDetails } from '../features/drinks/drinksSlice'

export default function DrinkList() {
  const dispatch = useDispatch()
  const { items, loading, error, filter, selected } = useSelector(s => s.drinks)

  if (loading) return <p className="status">Loading drinks...</p>
  if (error) return <p className="status error">{error}</p>
  const filtered = items.filter(d => {
    if (filter === 'alcoholic') return (d.alcoholic || '').toLowerCase().includes('alcoholic')
    if (filter === 'non-alcoholic') return (d.alcoholic || '').toLowerCase().includes('non alcoholic')
    return true
  })
  if (!filtered.length) return <p className="status">No drinks found. Try another search.</p>

  return (
    <>
      <div className="grid">
        {filtered.map(d => (
          <DrinkCard key={d.id} drink={d} />
        ))}
      </div>
      {selected && (
        <DetailsModal drink={selected} onClose={() => dispatch(closeDetails())} />
      )}
    </>
  )
}
 *cascade08*cascade08[ *cascade08[√*cascade08√Ú *cascade08Úìì™ *cascade08™º*cascade08º› *cascade08›Ü*cascade08Üä *cascade08äã*cascade08ãå *cascade08åç*cascade08çè *cascade08è∆*cascade08∆« *cascade08«Ï*cascade08ÏÃ *cascade08Ã’’Î *cascade08ÎÏ*cascade08ÏÚ *cascade08ÚÛ*cascade08ÛÙ *cascade08Ùı*cascade08ıˆ *cascade08ˆ˜*cascade08˜˘ *cascade08˘¸*cascade08¸à *cascade08àâ*cascade08âë *cascade08ëí*cascade08íª *cascade08ªΩ*cascade08Ω¡ *cascade08¡√*cascade08√Ã *cascade08Ã≈*cascade08≈Õ *cascade082Cfile:///Users/dam113/Desktop/liquorose/src/components/DrinkList.jsx