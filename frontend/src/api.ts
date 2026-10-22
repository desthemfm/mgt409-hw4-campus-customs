// Typed helpers for the FastAPI backend. Shapes mirror the Pydantic models in backend/main.py.

export type SizeStock = { size: string; quantity: number }

// Mirrors ProductCard in backend/models.py. (Named ProductSummary here because ProductCard
// is the name of the React component that draws it.)
export type ProductSummary = {
  product_id: string
  name: string
  category: string
  garment_type: string
  description: string
  short_info: string
  price: number
  image_url: string
  total_stock: number
  in_stock: boolean
  sizes_in_stock: string[]
  low_stock_note: string | null // e.g. "Only 2 left in XL", from live inventory
}

export type ProductDetail = ProductSummary & {
  colors: string[]
  search_tags: string[]
  inventory: SizeStock[]
}

export type Category = { name: string; count: number }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, { signal })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(0, "We couldn't reach the shop server. Please make sure the backend is running.")
  }
  return parseResponse<T>(res)
}

async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    // Our own errors send a string; FastAPI's automatic validation errors send a list.
    const detail = Array.isArray(body?.detail) ? 'Please check the form and try again.' : body?.detail
    throw new ApiError(res.status, detail ?? `Request failed (${res.status})`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

async function postJson<T>(url: string, data: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin', // send and receive the login cookie
      body: JSON.stringify(data),
    })
  } catch {
    throw new ApiError(0, "We couldn't reach the shop server. Please make sure the backend is running.")
  }
  return parseResponse<T>(res)
}

export const formatPrice = (price: number) => `$${price.toFixed(2)}`

export function fetchProducts(params: { category?: string; q?: string } = {}, signal?: AbortSignal) {
  const qs = new URLSearchParams()
  if (params.category) qs.set('category', params.category)
  if (params.q) qs.set('q', params.q)
  const query = qs.toString()
  return getJson<ProductSummary[]>(`/api/products${query ? `?${query}` : ''}`, signal)
}

export function fetchProduct(productId: string, signal?: AbortSignal) {
  return getJson<ProductDetail>(`/api/products/${encodeURIComponent(productId)}`, signal)
}

export function fetchCategories(signal?: AbortSignal) {
  return getJson<Category[]>('/api/categories', signal)
}

// ---------- Accounts ----------

export type User = {
  id: number
  first_name: string
  last_name: string
  name: string
  email: string
  created_at: string
}

export type SignupData = {
  first_name: string
  last_name: string
  email: string
  password: string
  confirm_password: string
}

export const signup = (data: SignupData) => postJson<User>('/api/auth/signup', data)
export const login = (email: string, password: string) => postJson<User>('/api/auth/login', { email, password })
export const logout = () => postJson<void>('/api/auth/logout', {})
export const fetchMe = (signal?: AbortSignal) => getJson<User | null>('/api/auth/me', signal)
