¨	import { createSlice } from '@reduxjs/toolkit'

const initialState = {
  items: [],
  loading: false,
  error: null,
  query: '',
  filter: 'all',
  selected: null,
}

const drinksSlice = createSlice({
  name: 'drinks',
  initialState,
  reducers: {
    setQuery(state, action) {
      state.query = action.payload
    },
    setFilter(state, action) {
      state.filter = action.payload || 'all'
    },
    fetchDrinksRequested(state, action) {
      state.loading = true
      state.error = null
      if (typeof action.payload === 'string') {
        state.query = action.payload
      }
    },
    fetchDrinksSucceeded(state, action) {
      state.loading = false
      state.items = action.payload || []
    },
    fetchDrinksFailed(state, action) {
      state.loading = false
      state.error = action.payload || 'Failed to load drinks'
    },
    openDetails(state, action) {
      state.selected = action.payload || null
    },
    closeDetails(state) {
      state.selected = null
    },
  }
})

export const { setQuery, setFilter, fetchDrinksRequested, fetchDrinksSucceeded, fetchDrinksFailed, openDetails, closeDetails } = drinksSlice.actions
export default drinksSlice.reducer
€ *cascade08€¤ *cascade08¤Â *cascade08Â•*cascade08•Ó *cascade08Óç *cascade08çð *cascade08ðð*cascade08ð‡ *cascade08‡’*cascade08’Ñ *cascade08Ñì *cascade08ì¨	 *cascade082Ifile:///Users/dam113/Desktop/liquorose/src/features/drinks/drinksSlice.js