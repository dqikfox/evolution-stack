# E-commerce Checkout Pitfalls

Condensed reference for the specific class of silent checkout failures
that occur when the store page, checkout page, and backend API disagree
on field names or storage keys. Every rule here was discovered through
a real order that appeared to succeed but was undercharged or lost.

## localStorage key mismatch across pages

**Symptom:** Checkout page shows "Your cart is empty" even though the
store page added items. No JavaScript error in console — the keys
simply don't match.

**Root cause:** `store.html` writes to `krysys.cart` but
`store-checkout.html` reads from `kry_cart`. These are different
localStorage keys; the second returns `null` → `[]`.

**Prevention:**
```bash
grep -rn "localStorage.*cart" store.html store-checkout.html
```
Both files MUST show the exact same key string. Common variants that
cause drift:
- Namespace prefix: `krysys.cart` vs `cart`
- Abbreviation: `kry_cart` vs `krysys.cart`
- Hyphen vs dot: `krysys-cart` vs `krysys.cart`

**QA probe:**
Inject a test cart, then verify checkout reads it:
```js
localStorage.setItem('krysys.cart', JSON.stringify([{sku:'TEST', qty:1, price:10, label:'Test'}]));
```
Navigate to checkout and confirm the summary populates.

## Client-server field name contract mismatch (undercharging)

**Symptom:** Customer sees correct total at checkout, but the order
total stored in the database is wrong — e.g. 3× $8.80 items show as
$8.80 + $12 shipping = $20.80 instead of $26.40 + $12 = $38.40.

**Root cause:** The frontend sends `{sku, qty}` but the server expects
`{sku, quantity}`. The server destructures `quantity || 1`, so every
multi-item order is silently charged as quantity=1.

**Prevention:**
1. Before wiring checkout → API, list field names on both sides:
   ```bash
   grep -n "qty\|quantity" store.html store-checkout.html server.js
   ```
2. Map at the checkout boundary if names differ:
   ```js
   items: cart.map(it => ({ sku: it.sku, quantity: it.qty }))
   ```
3. Verify with `quantity > 1`:
   ```bash
   curl -s -X POST http://localhost:PORT/api/checkout \
     -H "Content-Type: application/json" \
     -d '{"items":[{"sku":"CRY-001","quantity":3}],"customer":{...},"payment_method":"payid"}'
   ```
   Response total MUST equal `unit_price * quantity + shipping`.

**Critical:** A total of `$12` for 3× `$8.80` items means the server
is still defaulting to `quantity=1`. This is a revenue bug — the
customer pays less than they should.

## Price field name drift between store and checkout

**Symptom:** Checkout summary shows `$NaN` or `$0.00` per line. Shipping
threshold logic (free over $100) never triggers.

**Root cause:** `store.html` saves `price: 12.00` but
`store-checkout.html` reads `it.price_usd`. The field is `undefined`,
so `qty * undefined` → `NaN`.

**Prevention:**
- Use defensive accessor that tries both names:
  ```js
  const unitPrice = it.price || it.price_usd || 0;
  ```
- After renaming a price field, grep the entire frontend for the old
  name — stale cart data in localStorage still carries it.

## Cross-page cart data shape mismatch

**Symptom:** Checkout renders items but shows wrong names, wrong
quantities, or the "Place Order" button errors with "Cannot read
property 'sku' of undefined".

**Root cause:** `store.html` pushes `{sku, label, price, image, qty}`
but `store-checkout.html` iterates expecting `{sku, name, price_usd,
quantity}`. Fields like `name` and `label` are semantically the same
but keyed differently.

**Prevention:**
Define a single cart item schema and transform at boundaries:
```js
// Store saves this shape
const cartItem = { sku, label, price, qty };

// Checkout sends this shape to server
const apiItem = { sku: cartItem.sku, quantity: cartItem.qty };

// Checkout renders using defensive reads
const name = cartItem.label || cartItem.name || cartItem.sku;
const price = cartItem.price || cartItem.price_usd || 0;
```

## End-to-end checkout verification recipe

After any change to cart, checkout, or the `/api/checkout` handler:

```bash
# 1. Verify localStorage keys match
grep -rn "localStorage.*cart" store.html store-checkout.html

# 2. Verify field names across frontend + backend
grep -n "qty\|quantity\|price\|price_usd" store.html store-checkout.html server.js

# 3. Place a test order with quantity > 1
curl -s -X POST http://localhost:PORT/api/checkout \
  -H "Content-Type: application/json" \
  -d '{"items":[{"sku":"REAL-SKU","quantity":3}],"customer":{"email":"test@test.com","firstName":"Test","lastName":"User","address":"1 St","city":"Sydney","postcode":"2000","state":"NSW","country":"Australia","phone":""},"payment_method":"payid"}'

# 4. Verify total in response matches expected
calc_total=$((qty * unit_price + shipping))

# 5. Verify order appears in admin data
# (requires admin auth — verify separately)
```

## When these bugs go unnoticed

All three bugs produce **silent failures** — no JavaScript exceptions,
no HTTP errors, no user-visible crashes. The customer just sees an
empty cart, a wrong total, or an undercharged order. The only way to
catch them is explicit cross-page field-name verification.
