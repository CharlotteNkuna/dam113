†import { configureStore } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import rootReducer from './reduce'
import rootSaga from './rootSaga'

const sagaMiddleware = createSagaMiddleware()

export const store = configureStore({
  reducer: rootReducer,
  middleware: (getDefault) => getDefault({ thunk: false }).concat(sagaMiddleware)
})

sagaMiddleware.run(rootSaga)
h *cascade08hk*cascade08k~ *cascade08~*cascade08‡ *cascade08‡Š*cascade08Š† *cascade0829file:///Users/dam113/Desktop/liquorose/src/store/store.js