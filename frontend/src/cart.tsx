// Shopping cart state, shared by the whole site and saved in the browser (localStorage)
// so it survives a page refresh. Prices here are a snapshot for quick display only;
// the Cart page re-checks live price and stock from the API.

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type CartItem = {
  product_id: string
  size: string
  quantity: number
  name: string
  price: number
  image_url: string
}

type CartContextValue = {
  items: CartItem[]
  count: number
  add: (item: Omit<CartItem, 'quantity'>, quantity: number, maxAvailable: number) => number
  setQuantity: (productId: string, size: string, quantity: number) => void
  remove: (productId: string, size: string) => void
  clear: () => void
  quantityOf: (productId: string, size: string) => number
}

const STORAGE_KEY = 'campus-customs-cart'
const CartContext = createContext<CartContextValue | null>(null)

function loadCart(): CartItem[] {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

const sameLine = (a: { product_id: string; size: string }, productId: string, size: string) =>
  a.product_id === productId && a.size === size

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>(loadCart)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  }, [items])

  const value = useMemo<CartContextValue>(() => {
    const quantityOf = (productId: string, size: string) =>
      items.find((i) => sameLine(i, productId, size))?.quantity ?? 0

    return {
      items,
      count: items.reduce((sum, i) => sum + i.quantity, 0),
      quantityOf,
      // Adds up to `quantity`, never past what is in stock. Returns how many were actually added.
      add(item, quantity, maxAvailable) {
        const already = quantityOf(item.product_id, item.size)
        const added = Math.max(0, Math.min(quantity, maxAvailable - already))
        if (added === 0) return 0
        setItems((prev) =>
          already > 0
            ? prev.map((i) => (sameLine(i, item.product_id, item.size) ? { ...i, quantity: i.quantity + added } : i))
            : [...prev, { ...item, quantity: added }],
        )
        return added
      },
      setQuantity(productId, size, quantity) {
        setItems((prev) =>
          quantity <= 0
            ? prev.filter((i) => !sameLine(i, productId, size))
            : prev.map((i) => (sameLine(i, productId, size) ? { ...i, quantity } : i)),
        )
      },
      remove(productId, size) {
        setItems((prev) => prev.filter((i) => !sameLine(i, productId, size)))
      },
      clear() {
        setItems([])
      },
    }
  }, [items])

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used inside <CartProvider>')
  return ctx
}
