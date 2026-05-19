½import axios from 'axios'

const BASE_URL = 'https://www.thecocktaildb.com/api/json/v1/1'

export async function searchDrinks(query) {
  const q = (query || '').trim()
  const url = `${BASE_URL}/search.php?s=${encodeURIComponent(q || 'margarita')}`
  const { data } = await axios.get(url)
  const list = Array.isArray(data?.drinks) ? data.drinks : []
  return list.map(d => ({
    id: d.idDrink,
    name: d.strDrink,
    category: d.strCategory,
    alcoholic: d.strAlcoholic,
    glass: d.strGlass,
    instructions: d.strInstructions,
    thumb: d.strDrinkThumb
  }))
}
½*cascade082Gfile:///Users/dam113/Desktop/liquorose/src/features/drinks/drinksApi.js