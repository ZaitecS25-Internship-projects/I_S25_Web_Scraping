# Configuración de Stripe para Suscripciones Premium

## 1. Crear cuenta en Stripe

1. Visita [https://dashboard.stripe.com/register](https://dashboard.stripe.com/register)
2. Crea tu cuenta de Stripe
3. Activa el modo de prueba (Test Mode) para desarrollo

## 2. Obtener claves de API

1. Ve a [https://dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys)
2. Copia la **Publishable key** (empieza con `pk_test_`)
3. Revela y copia la **Secret key** (empieza con `sk_test_`)
4. Añade ambas claves a tu archivo `.env`:

```env
STRIPE_SECRET_KEY=sk_test_tu_clave_secreta_aqui
STRIPE_PUBLISHABLE_KEY=pk_test_tu_clave_publica_aqui
```

## 3. Crear productos y precios

### Plan Mensual (€9.99/mes)

1. Ve a [https://dashboard.stripe.com/products/create](https://dashboard.stripe.com/products/create)
2. Configura el producto:
   - **Nombre**: Premium Mensual
   - **Descripción**: Acceso premium con facturación mensual
   - **Tipo de precio**: Recurrente
   - **Precio**: €9.99
   - **Frecuencia de facturación**: Mensual
   - **Moneda**: EUR
3. Haz clic en "Guardar producto"
4. Copia el **Price ID** (empieza con `price_`)
5. Añádelo a tu `.env`:

```env
STRIPE_PRICE_MONTHLY=price_1234567890abcdefg
```

### Plan Anual (€44.99/año)

1. Crea otro producto:
   - **Nombre**: Premium Anual
   - **Descripción**: Acceso premium con facturación anual (ahorra €24.89)
   - **Tipo de precio**: Recurrente
   - **Precio**: €44.99
   - **Frecuencia de facturación**: Anual
   - **Moneda**: EUR
2. Guarda el producto
3. Copia el **Price ID** y añádelo a tu `.env`:

```env
STRIPE_PRICE_ANNUAL=price_0987654321zyxwvut
```

## 4. Configurar webhook

1. Ve a [https://dashboard.stripe.com/webhooks](https://dashboard.stripe.com/webhooks)
2. Haz clic en "Add endpoint"
3. Configura el endpoint:
   - **URL del endpoint**: `https://tu-dominio.com/webhook` (o `http://localhost:5000/webhook` para desarrollo local)
   - **Eventos a escuchar**:
     - `checkout.session.completed` - Cuando se completa el pago
     - `customer.subscription.updated` - Cuando cambia una suscripción
     - `customer.subscription.deleted` - Cuando se cancela una suscripción
4. Haz clic en "Add endpoint"
5. Copia el **Signing secret** (empieza con `whsec_`)
6. Añádelo a tu `.env`:

```env
STRIPE_WEBHOOK_SECRET=whsec_tu_secreto_webhook_aqui
```

## 5. Probar webhooks en local (opcional)

Para probar webhooks en tu entorno local:

1. Instala Stripe CLI:
   - Windows: `scoop install stripe`
   - Descarga directa: [https://github.com/stripe/stripe-cli/releases](https://github.com/stripe/stripe-cli/releases)

2. Inicia sesión:
   ```bash
   stripe login
   ```

3. Reenvía webhooks a tu servidor local:
   ```bash
   stripe listen --forward-to localhost:5000/webhook
   ```

4. El CLI mostrará un webhook secret temporal - úsalo en tu `.env` para pruebas

## 6. Archivo .env completo

Tu archivo `.env` debe verse así:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=8523147291:AAF4XPDTHDUstHvEcOLc7pgUDMiWSYt85JU

# Stripe Payment Keys
STRIPE_SECRET_KEY=sk_test_51AbCdEfGh...
STRIPE_PUBLISHABLE_KEY=pk_test_51AbCdEfGh...

# Stripe Webhook Secret
STRIPE_WEBHOOK_SECRET=whsec_1234567890...

# Stripe Price IDs
STRIPE_PRICE_MONTHLY=price_1AbCdEfGh
STRIPE_PRICE_ANNUAL=price_1ZyXwVuTsR
```

## 7. Probar el flujo de pago

### Modo de prueba

Stripe proporciona tarjetas de prueba:

**Pago exitoso:**
- Número: `4242 4242 4242 4242`
- Fecha: Cualquier fecha futura
- CVC: Cualquier 3 dígitos
- Código postal: Cualquier 5 dígitos

**Pago rechazado:**
- Número: `4000 0000 0000 0002`

**Requiere autenticación 3D Secure:**
- Número: `4000 0025 0000 3155`

### Flujo completo

1. Inicia la aplicación Flask
2. Inicia sesión como usuario
3. Ve a "Centro de suscripciones"
4. Selecciona un plan (Mensual o Anual)
5. Completa el checkout con tarjeta de prueba
6. Verifica que la suscripción se active en la base de datos
7. Comprueba que aparece en tu panel

## 8. Pasar a producción

Cuando estés listo para aceptar pagos reales:

1. Ve a [https://dashboard.stripe.com/settings](https://dashboard.stripe.com/settings)
2. Completa la verificación de tu cuenta
3. Cambia al modo "Live" (producción)
4. Obtén las claves de producción (empiezan con `pk_live_` y `sk_live_`)
5. Crea los productos y precios en modo Live
6. Configura el webhook en modo Live con tu URL real
7. Actualiza tu `.env` con las claves de producción

## 9. Monitoreo

- **Dashboard de Stripe**: [https://dashboard.stripe.com](https://dashboard.stripe.com)
- **Pagos**: Ver todos los pagos y suscripciones
- **Logs**: Ver eventos de webhook
- **Clientes**: Gestionar información de clientes
- **Disputas**: Manejar chargebacks

## 10. Soporte

- Documentación oficial: [https://stripe.com/docs](https://stripe.com/docs)
- API Reference: [https://stripe.com/docs/api](https://stripe.com/docs/api)
- Comunidad: [https://support.stripe.com](https://support.stripe.com)
