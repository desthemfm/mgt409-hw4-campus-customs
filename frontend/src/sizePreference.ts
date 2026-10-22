// "Shop your size" (Problem 9, front-end improvement): the shopper's size, remembered in this browser.
// Used by the Products page size filter and to preselect the size on product pages.

export const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'] as const
const KEY = 'campus-customs-size'

export function getPreferredSize(): string | null {
  const s = localStorage.getItem(KEY)
  return s && (SIZES as readonly string[]).includes(s) ? s : null
}

export function setPreferredSize(size: string | null) {
  if (size) localStorage.setItem(KEY, size)
  else localStorage.removeItem(KEY)
}
