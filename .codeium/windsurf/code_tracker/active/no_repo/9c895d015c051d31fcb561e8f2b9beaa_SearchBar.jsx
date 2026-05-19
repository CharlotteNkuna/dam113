åimport { useDispatch, useSelector } from 'react-redux'
import { useState, useEffect } from 'react'
import { fetchDrinksRequested, setQuery } from '../features/drinks/drinksSlice'

export default function SearchBar() {
  const dispatch = useDispatch()
  const query = useSelector(s => s.drinks.query)
  const [local, setLocal] = useState(query)

  useEffect(() => {
    if (!query) {
      dispatch(fetchDrinksRequested(''))
    }
  }, [dispatch, query])

  function onSubmit(e) {
    e.preventDefault()
    dispatch(setQuery(local))
    dispatch(fetchDrinksRequested(local))
  }

  return (
    <form className="searchbar" onSubmit={onSubmit}>
      <input
        aria-label="Search drinks"
        placeholder="Search cocktails (e.g., margarita)"
        value={local}
        onChange={(e) => {
          const v = e.target.value
          setLocal(v)
          dispatch(setQuery(v)) // debounced fetch via saga
        }}
      />
      <button type="submit">Search</button>
    </form>
  )
}
œ *cascade08œ««­ *cascade08­²*cascade08²À *cascade08ÀÕ*cascade08ÕÖ *cascade08Öœ*cascade08œå *cascade082Cfile:///Users/dam113/Desktop/liquorose/src/components/SearchBar.jsx