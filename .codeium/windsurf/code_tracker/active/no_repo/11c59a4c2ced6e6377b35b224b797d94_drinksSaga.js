Úimport { call, put, takeLatest, debounce } from 'redux-saga/effects'
import { fetchDrinksRequested, fetchDrinksSucceeded, fetchDrinksFailed, setQuery } from './drinksSlice'
import { searchDrinks } from './drinksApi'

function* handleFetchDrinks(action) {
  try {
    const items = yield call(searchDrinks, action.payload)
    yield put(fetchDrinksSucceeded(items))
  } catch (err) {
    yield put(fetchDrinksFailed(err?.message || 'Unknown error'))
  }
}

export default function* drinksSaga() {
  // Manual fetch
  yield takeLatest(fetchDrinksRequested.type, handleFetchDrinks)
  // Debounced search from typing
  yield debounce(400, setQuery.type, function* (action) {
    yield put(fetchDrinksRequested(action.payload))
  })
}
 *cascade08(*cascade08(‹ *cascade08‹•*cascade08•ò *cascade08ò„*cascade08„Á *cascade08ÁŸ *cascade08ŸŸ*cascade08ŸÖ *cascade08ÖÚ *cascade082Hfile:///Users/dam113/Desktop/liquorose/src/features/drinks/drinksSaga.js