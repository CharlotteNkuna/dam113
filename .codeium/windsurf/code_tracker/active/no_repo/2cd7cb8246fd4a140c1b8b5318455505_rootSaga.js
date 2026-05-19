·import { all, fork } from 'redux-saga/effects'
import drinksSaga from '../features/drinks/drinksSaga'

export default function* rootSaga() {
  yield all([
    fork(drinksSaga)
  ])
}
·*cascade082<file:///Users/dam113/Desktop/liquorose/src/store/rootSaga.js