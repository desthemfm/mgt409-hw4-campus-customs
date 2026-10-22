// Hand-picked product IDs for the home page. Names, prices, and photos come live from the API.
export const PRIDE_PICK_IDS = [
  'basic-hoodie-big-yale',
  'boola-boola-t-shirt',
  '2025-yale-vs-harvard-t-shirt',
  'yale-sports-hoodie-hockey',
]

export const FALL_PICK_IDS = [
  'hype-and-vice-yale-university-premium-crewneck',
  'berkeley-1-4-zip',
  'benjamin-franklin-fleece-jacket',
  'brooks-brothers-bomber-jacket-yale',
]

// Order of the category tiles and the product shown on each one.
export const CATEGORY_TILES = [
  { name: 'T-Shirts', productId: 'boola-boola-t-shirt' },
  { name: 'Crewnecks', productId: 'super-heavyweight-crewneck-arched-yale-crest' },
  { name: 'Hoodies', productId: 'basic-hoodie-big-yale' },
  { name: 'Quarter-Zips', productId: 'berkeley-1-4-zip' },
  { name: 'Jackets', productId: 'brooks-brothers-bomber-jacket-yale' },
  { name: 'Long Sleeves', productId: 'dry-zone-long-sleeve' },
]

export const productImage = (productId: string) => `/media/products/${productId}.jpg`
