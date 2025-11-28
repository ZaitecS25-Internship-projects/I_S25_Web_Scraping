"""
Rutas para gestión de suscripciones Premium con Stripe
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import os
import stripe
from app.db import get_users_db

subscription_bp = Blueprint('subscription', __name__)

# Configurar Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_TU_CLAVE_SECRETA')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', 'pk_test_TU_CLAVE_PUBLICA')

# IDs de precios de Stripe (crear en el dashboard de Stripe)
PRICE_MONTHLY = os.getenv('STRIPE_PRICE_MONTHLY', 'price_monthly_id')
PRICE_ANNUAL = os.getenv('STRIPE_PRICE_ANNUAL', 'price_annual_id')


@subscription_bp.route('/suscripciones')
@login_required
def centro_suscripciones():
    """Página principal del centro de suscripciones"""
    db = get_users_db()
    
    # Obtener suscripción actual del usuario
    suscripcion = db.execute(
        "SELECT * FROM suscripciones_premium WHERE user_id = ? AND estado = 'activa'",
        (current_user.id,)
    ).fetchone()
    
    db.close()
    
    return render_template(
        'subscription/centro_suscripciones.html',
        suscripcion=suscripcion,
        stripe_key=STRIPE_PUBLISHABLE_KEY
    )


@subscription_bp.route('/crear-checkout-session', methods=['POST'])
@login_required
def crear_checkout_session():
    """Crear sesión de pago con Stripe Checkout"""
    plan = request.form.get('plan')  # 'monthly' o 'annual'
    
    if plan == 'monthly':
        price_id = PRICE_MONTHLY
    elif plan == 'annual':
        price_id = PRICE_ANNUAL
    else:
        flash('Plan no válido', 'error')
        return redirect(url_for('subscription.centro_suscripciones'))
    
    # Verificar si Stripe está configurado
    if stripe.api_key == 'sk_test_TU_CLAVE_SECRETA' or 'tu_clave_secreta_aqui' in stripe.api_key:
        flash('⚠️ Stripe no está configurado. Consulta STRIPE_SETUP.md para obtener tus claves de API.', 'warning')
        return redirect(url_for('subscription.centro_suscripciones'))
    
    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('subscription.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('subscription.centro_suscripciones', _external=True),
            metadata={
                'user_id': current_user.id,
                'plan': plan
            }
        )
        
        return redirect(checkout_session.url, code=303)
    
    except Exception as e:
        flash(f'Error al crear la sesión de pago: {str(e)}', 'error')
        return redirect(url_for('subscription.centro_suscripciones'))


@subscription_bp.route('/success')
@login_required
def success():
    """Página de éxito después del pago"""
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('Sesión no válida', 'error')
        return redirect(url_for('subscription.centro_suscripciones'))
    
    try:
        # Recuperar sesión de Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == 'paid':
            # Activar suscripción en la base de datos
            db = get_users_db()
            
            plan = session.metadata.get('plan')
            
            # Calcular fecha de fin según el plan
            if plan == 'monthly':
                fecha_fin = datetime.now() + timedelta(days=30)
                plan_nombre = 'Plan Premium Mensual'
                precio = 9.99
            else:
                fecha_fin = datetime.now() + timedelta(days=365)
                plan_nombre = 'Plan Premium Anual'
                precio = 44.99
            
            # Insertar o actualizar suscripción
            db.execute("""
                INSERT INTO suscripciones_premium 
                (user_id, plan, precio, fecha_inicio, fecha_fin, stripe_subscription_id, estado)
                VALUES (?, ?, ?, ?, ?, ?, 'activa')
                ON CONFLICT(user_id) DO UPDATE SET
                    plan = excluded.plan,
                    precio = excluded.precio,
                    fecha_inicio = excluded.fecha_inicio,
                    fecha_fin = excluded.fecha_fin,
                    stripe_subscription_id = excluded.stripe_subscription_id,
                    estado = 'activa'
            """, (
                current_user.id,
                plan_nombre,
                precio,
                datetime.now().isoformat(),
                fecha_fin.isoformat(),
                session.subscription
            ))
            
            db.commit()
            db.close()
            
            flash('¡Suscripción activada con éxito! 🎉', 'success')
        else:
            flash('El pago no se completó correctamente', 'error')
    
    except Exception as e:
        flash(f'Error al verificar el pago: {str(e)}', 'error')
    
    return redirect(url_for('user.configuracion_cuenta'))


@subscription_bp.route('/cancelar-suscripcion', methods=['POST'])
@login_required
def cancelar_suscripcion():
    """Cancelar suscripción activa"""
    db = get_users_db()
    
    suscripcion = db.execute(
        "SELECT * FROM suscripciones_premium WHERE user_id = ? AND estado = 'activa'",
        (current_user.id,)
    ).fetchone()
    
    if not suscripcion:
        flash('No tienes ninguna suscripción activa', 'error')
        db.close()
        return redirect(url_for('subscription.centro_suscripciones'))
    
    try:
        # Cancelar en Stripe
        if suscripcion['stripe_subscription_id']:
            stripe.Subscription.delete(suscripcion['stripe_subscription_id'])
        
        # Actualizar estado en la base de datos
        db.execute(
            "UPDATE suscripciones_premium SET estado = 'cancelada', fecha_cancelacion = ? WHERE user_id = ?",
            (datetime.now().isoformat(), current_user.id)
        )
        db.commit()
        
        flash('Suscripción cancelada correctamente', 'success')
    
    except Exception as e:
        flash(f'Error al cancelar la suscripción: {str(e)}', 'error')
    
    finally:
        db.close()
    
    return redirect(url_for('subscription.centro_suscripciones'))


@subscription_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Webhook para eventos de Stripe"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Manejar eventos de Stripe
    if event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        # Marcar como cancelada en la base de datos
        db = get_users_db()
        db.execute(
            "UPDATE suscripciones_premium SET estado = 'cancelada' WHERE stripe_subscription_id = ?",
            (subscription['id'],)
        )
        db.commit()
        db.close()
    
    elif event['type'] == 'invoice.payment_succeeded':
        # Renovación exitosa
        invoice = event['data']['object']
        subscription_id = invoice['subscription']
        
        db = get_users_db()
        # Extender fecha de fin
        db.execute("""
            UPDATE suscripciones_premium 
            SET fecha_fin = datetime(fecha_fin, '+30 days')
            WHERE stripe_subscription_id = ?
        """, (subscription_id,))
        db.commit()
        db.close()
    
    elif event['type'] == 'invoice.payment_failed':
        # Pago fallido
        invoice = event['data']['object']
        subscription_id = invoice['subscription']
        
        db = get_users_db()
        db.execute(
            "UPDATE suscripciones_premium SET estado = 'pago_fallido' WHERE stripe_subscription_id = ?",
            (subscription_id,)
        )
        db.commit()
        db.close()
    
    return jsonify({'status': 'success'}), 200


def init_subscription_db():
    """Inicializar tabla de suscripciones premium (diferente de la tabla de newsletters)"""
    db = get_users_db()
    
    # Verificar si existe la tabla suscripciones_premium
    cursor = db.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='suscripciones_premium'
    """)
    
    if cursor.fetchone() is None:
        # Crear nueva tabla para suscripciones premium
        db.execute("""
            CREATE TABLE suscripciones_premium (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                plan TEXT NOT NULL,
                precio REAL NOT NULL,
                fecha_inicio TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                fecha_cancelacion TEXT,
                stripe_subscription_id TEXT,
                stripe_customer_id TEXT,
                estado TEXT NOT NULL DEFAULT 'activa',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        db.commit()
    
    db.close()
