"""
Ruta de prueba para activar/desactivar premium sin pagar (solo para desarrollo)
"""
from flask import Blueprint, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.db import get_users_db

test_premium_bp = Blueprint('test_premium', __name__)


@test_premium_bp.route('/activar-premium-prueba')
@login_required
def activar_premium_prueba():
    """Activa una suscripción premium de prueba (30 días) sin pagar"""
    db = get_users_db()
    
    try:
        # Verificar si ya tiene suscripción activa
        suscripcion_existente = db.execute(
            "SELECT * FROM suscripciones_premium WHERE user_id = ? AND estado = 'activa'",
            (current_user.id,)
        ).fetchone()
        
        if suscripcion_existente:
            flash('Ya tienes una suscripción premium activa', 'info')
        else:
            # Crear suscripción de prueba por 30 días
            fecha_inicio = datetime.now()
            fecha_fin = fecha_inicio + timedelta(days=30)
            
            db.execute("""
                INSERT INTO suscripciones_premium 
                (user_id, plan, precio, fecha_inicio, fecha_fin, stripe_subscription_id, estado)
                VALUES (?, ?, ?, ?, ?, ?, 'activa')
                ON CONFLICT(user_id) DO UPDATE SET
                    plan = excluded.plan,
                    precio = excluded.precio,
                    fecha_inicio = excluded.fecha_inicio,
                    fecha_fin = excluded.fecha_fin,
                    estado = 'activa'
            """, (
                current_user.id,
                'Plan Premium Prueba (30 días)',
                0.00,
                fecha_inicio.isoformat(),
                fecha_fin.isoformat(),
                'test_subscription_' + str(current_user.id)
            ))
            
            db.commit()
            flash('✅ Premium de prueba activado por 30 días', 'success')
    
    except Exception as e:
        flash(f'Error al activar premium de prueba: {str(e)}', 'error')
    
    finally:
        db.close()
    
    return redirect(url_for('subscription.centro_suscripciones'))


@test_premium_bp.route('/desactivar-premium-prueba')
@login_required
def desactivar_premium_prueba():
    """Desactiva la suscripción premium de prueba"""
    db = get_users_db()
    
    try:
        db.execute(
            "UPDATE suscripciones_premium SET estado = 'cancelada', fecha_cancelacion = ? WHERE user_id = ?",
            (datetime.now().isoformat(), current_user.id)
        )
        db.commit()
        flash('Premium de prueba desactivado', 'info')
    
    except Exception as e:
        flash(f'Error al desactivar premium: {str(e)}', 'error')
    
    finally:
        db.close()
    
    return redirect(url_for('subscription.centro_suscripciones'))
