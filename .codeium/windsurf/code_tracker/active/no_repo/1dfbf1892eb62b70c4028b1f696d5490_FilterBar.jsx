Áimport { useDispatch, useSelector } from 'react-redux'
import { setFilter } from '../features/drinks/drinksSlice'

export default function FilterBar() {
  const dispatch = useDispatch()
  const filter = useSelector(s => s.drinks.filter)

  return (
    <div className="filterbar">
      <button className={`chip ${filter==='all'?'active':''}`} onClick={() => dispatch(setFilter('all'))}>All</button>
      <button className={`chip ${filter==='alcoholic'?'active':''}`} onClick={() => dispatch(setFilter('alcoholic'))}>Alcoholic</button>
      <button className={`chip ${filter==='non-alcoholic'?'active':''}`} onClick={() => dispatch(setFilter('non-alcoholic'))}>Nonâ€‘alcoholic</button>
    </div>
  )
}
Á*cascade082Cfile:///Users/dam113/Desktop/liquorose/src/components/FilterBar.jsx