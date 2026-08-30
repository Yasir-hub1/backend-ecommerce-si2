# API POS — FashionStore

Base URL: `/api/v1/pos/`

**Autenticación:** JWT (`Authorization: Bearer <token>`)

**Permisos:** rol `CASHIER` o `BRANCH_MANAGER` con permiso RBAC `pos.sales`. El cajero solo opera sobre su sucursal asignada (`employee_profile.branch`).

**Moneda:** BOB

---

## Flujo recomendado en caja

1. Buscar producto → `GET /search/` o `GET /lookup/`
2. (Opcional) Cotizar carrito → `POST /quote/`
3. (Opcional) Validar pago mixto y vuelto → `POST /payments/preview/`
4. Cobrar → `POST /sales/checkout/`
5. Imprimir comprobante → `GET /sales/{id}/receipt/pdf/`
6. Cierre del día → `GET /daily-summary/`

---

## 1. Búsqueda rápida (nombre, SKU o código de barras)

### `GET /api/v1/pos/search/?q={texto}&limit=20`

Busca variantes activas. Si `q` coincide exactamente con barcode o SKU, devuelve un solo resultado.

**Query params**

| Param | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `q` | string | sí | Texto de búsqueda |
| `limit` | int | no | Máx. resultados (default 20, máx. 50) |

**Respuesta 200**

```json
{
  "count": 1,
  "results": [
    {
      "variant_id": 12,
      "product_id": 3,
      "product_name": "Camisa Oxford Slim",
      "sku": "OXF-M-BLU",
      "barcode": "7700123456789",
      "size": "M",
      "color": "Azul",
      "unit_price": "289.00",
      "stock": {
        "on_hand": 8,
        "reserved": 1,
        "available": 7
      }
    }
  ]
}
```

---

## 2. Lookup por escáner (código de barras / SKU)

### `GET /api/v1/pos/lookup/?barcode={codigo}`

Resolución exacta para pistola lectora. Equivalente a búsqueda exacta por barcode o SKU.

**Respuesta 200:** mismo objeto de variante que en `search`.

**Respuesta 404:** variante no encontrada.

---

## 3. Cotizar carrito (sin cobrar)

### `POST /api/v1/pos/quote/`

Calcula subtotales antes de registrar la venta.

**Body**

```json
{
  "items": [
    { "variant_id": 12, "quantity": 2 },
    { "variant_id": 15, "quantity": 1 }
  ]
}
```

**Respuesta 200**

```json
{
  "items": [
    {
      "variant_id": 12,
      "product_name": "Camisa Oxford Slim",
      "quantity": 2,
      "unit_price": "289.00",
      "line_subtotal": "578.00",
      "available": true,
      "stock": { "on_hand": 8, "reserved": 1, "available": 7 }
    }
  ],
  "subtotal": "578.00",
  "tax_total": "0.00",
  "grand_total": "578.00",
  "currency": "BOB"
}
```

---

## 4. Preview de pago mixto y vuelto

### `POST /api/v1/pos/payments/preview/`

Valida que el pago cubra el total y calcula el **vuelto** en efectivo.

**Body**

```json
{
  "items": [
    { "variant_id": 12, "quantity": 1 }
  ],
  "payments": [
    {
      "method": "CASH",
      "amount": "100.00",
      "received_amount": "150.00"
    },
    {
      "method": "CARD_POS",
      "amount": "189.00"
    }
  ]
}
```

**Métodos de pago POS:** `CASH`, `CARD_POS` (también acepta `QR`, `TRANSFER` si se envían).

**Respuesta 200**

```json
{
  "quote": { "...": "..." },
  "payment_summary": {
    "total_due": "289.00",
    "total_payment": "289.00",
    "total_change": "50.00",
    "overpayment": "0.00",
    "payments": [
      {
        "method": "CASH",
        "amount": "100.00",
        "received_amount": "150.00",
        "change_amount": "50.00"
      },
      {
        "method": "CARD_POS",
        "amount": "189.00",
        "change_amount": "0.00"
      }
    ]
  }
}
```

**Errores:** `400 INSUFFICIENT_PAYMENT` si la suma de pagos es menor al total.

---

## 5. Registrar venta presencial

### `POST /api/v1/pos/sales/checkout/`

Crea la orden en estado `PAID`, descuenta inventario, registra pagos, genera comprobante PDF.

> **Alias legacy:** `POST /api/v1/pos/sales/` (misma operación, mantener compatibilidad).

**Body**

```json
{
  "items": [
    { "variant_id": 12, "quantity": 1 }
  ],
  "payments": [
    {
      "method": "CASH",
      "amount": "100.00",
      "received_amount": "150.00"
    },
    {
      "method": "CARD_POS",
      "amount": "189.00"
    }
  ],
  "customer_id": 5,
  "reservation_id": 42
}
```

| Campo | Requerido | Descripción |
|-------|-----------|-------------|
| `items` | sí | Líneas vendidas |
| `payments` | sí | Uno o más métodos (pago mixto) |
| `customer_id` | no | ID del **User** del cliente |
| `reservation_id` | no | Venta desde reserva (ver sección 7) |

**Respuesta 201**

```json
{
  "message": "Venta registrada exitosamente",
  "order": {
    "id": 101,
    "code": "ORD-00000101",
    "status": "PAID",
    "grand_total": "289.00",
    "items": [ "..." ],
    "payments": [
      {
        "method": "CASH",
        "amount": "100.00",
        "received_amount": "150.00",
        "change_amount": "50.00"
      }
    ]
  },
  "receipt": {
    "id": 55,
    "receipt_number": "SCZ-01-000055",
    "pdf_url": "http://localhost:8000/api/v1/pos/sales/101/receipt/pdf/"
  },
  "total_change": "50.00"
}
```

**Errores frecuentes**

| Código | HTTP | Significado |
|--------|------|-------------|
| `INSUFFICIENT_STOCK` | 409 | Sin stock disponible |
| `INSUFFICIENT_PAYMENT` | 400 | Pagos no cubren el total |
| `INVALID_RESERVATION_STATUS` | 409 | Reserva no está `READY` o `IN_FITTING` |
| `INVALID_RESERVATION_QUANTITY` | 400 | Cantidad vendida > reservada |
| `BRANCH_MISMATCH` | 400 | Reserva de otra sucursal |

---

## 6. Comprobante (emisión e impresión)

### `GET /api/v1/pos/sales/{id}/receipt/`

Metadatos del comprobante.

**Respuesta 200**

```json
{
  "id": 55,
  "receipt_number": "SCZ-01-000055",
  "pdf_url": "/api/v1/pos/sales/101/receipt/pdf/",
  "order_code": "ORD-00000101"
}
```

### `GET /api/v1/pos/sales/{id}/receipt/pdf/`

Devuelve el PDF listo para imprimir (`Content-Type: application/pdf`).

También disponible vía órdenes generales: `GET /api/v1/orders/{id}/receipt/pdf/`.

---

## 7. Venta desde reserva (prendas que se lleva el cliente)

### `GET /api/v1/pos/reservations/lookup/?code=RSV-XXXXXXXX`

Obtiene el detalle de la reserva en la sucursal del cajero.

**Query:** `code` (código RSV) **o** `id` (PK numérico).

**Respuesta 200:** objeto `ReservationDetailSerializer` con ítems, variantes y estados.

### Cobro parcial o total

En `POST /sales/checkout/` envía:

- `reservation_id`: ID de la reserva
- `items`: **solo las prendas que el cliente compra** (subset de la reserva)

Comportamiento:

- Valida cantidades ≤ reservadas
- Descuenta stock con movimiento `OUT_SALE_RESERVED`
- Libera stock no comprado (`RESERVE_RELEASE`)
- Marca ítems como `PURCHASED` o `RETURNED_TO_FLOOR`
- Completa la reserva (`COMPLETED`)

La reserva debe estar en estado **`READY`** o **`IN_FITTING`**.

---

## 8. Ventas del día de la caja

### `GET /api/v1/pos/daily-summary/?date=2026-08-29`

Resumen de ventas POS del cajero autenticado en su sucursal.

**Query:** `date` (ISO, opcional; default = hoy)

**Respuesta 200**

```json
{
  "date": "2026-08-29",
  "branch_id": 1,
  "branch_code": "SCZ-01",
  "cashier_id": 8,
  "cashier_name": "María López",
  "order_count": 12,
  "total_sales": "3603.57",
  "currency": "BOB",
  "by_payment_method": {
    "CASH": { "total": "1200.00", "count": 5 },
    "CARD_POS": { "total": "2403.57", "count": 8 }
  }
}
```

### Listado de ventas POS

### `GET /api/v1/pos/sales/?paid_at__date=2026-08-29`

Lista paginada de órdenes POS del cajero (managers ven todas las de la sucursal).

### `GET /api/v1/pos/sales/{id}/`

Detalle completo con ítems, pagos y URL del comprobante.

---

## Endpoints relacionados (fuera de `/pos/`)

| Endpoint | Uso en POS |
|----------|------------|
| `GET /api/v1/variants/lookup/?barcode=` | Lookup alternativo (catálogo) |
| `GET /api/v1/reservations/today/` | Reservas del día en sucursal |
| `POST /api/v1/reservations/{id}/transition/` | Pasar reserva a `IN_FITTING` antes de cobrar |
| `GET /api/v1/orders/?channel=POS&created_at__date=` | Listado legacy de ventas POS |

---

## Permiso RBAC

Código: **`pos.sales`** — asignado por defecto a roles `CASHIER` y `BRANCH_MANAGER` (ver seed RBAC).

---

## Notas de implementación

- Las ventas POS usan el modelo unificado `Order` con `channel=POS`.
- El vuelto se calcula solo en pagos `CASH` cuando `received_amount > amount`.
- El comprobante PDF se genera automáticamente al registrar la venta.
- Los totales fiscales (`subtotal`, `grand_total`) quedan congelados en la orden.
