"""
Decorador y funciones auxiliares para gestionar características premium
"""
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user
import sqlite3
from datetime import datetime


def get_user_subscription(user_id):
    """
    Obtiene la suscripción activa de un usuario
    
    Args:
        user_id: ID del usuario
        
    Returns:
        dict: Información de la suscripción o None si no tiene suscripción activa
    """
    conn = sqlite3.connect('usuarios.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM suscripciones_premium 
        WHERE user_id = ? 
        AND estado = 'activa' 
        AND (fecha_fin IS NULL OR fecha_fin > ?)
    ''', (user_id, datetime.now().isoformat()))
    
    suscripcion = cursor.fetchone()
    conn.close()
    
    if suscripcion:
        return dict(suscripcion)
    return None


def is_premium(user_id):
    """
    Verifica si un usuario tiene una suscripción premium activa
    
    Args:
        user_id: ID del usuario
        
    Returns:
        bool: True si tiene suscripción activa, False en caso contrario
    """
    suscripcion = get_user_subscription(user_id)
    return suscripcion is not None


def require_premium(f):
    """
    Decorador para proteger rutas que requieren suscripción premium
    
    Uso:
        @app.route('/feature-premium')
        @login_required
        @require_premium
        def premium_feature():
            # Código de la característica premium
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debes iniciar sesión para acceder a esta función', 'warning')
            return redirect(url_for('auth.login'))
        
        if not is_premium(current_user.id):
            flash('Esta función requiere una suscripción premium. ¡Actualiza tu cuenta para acceder!', 'info')
            return redirect(url_for('subscription.centro_suscripciones'))
        
        return f(*args, **kwargs)
    return decorated_function


def get_premium_limits(user_id):
    """
    Obtiene los límites de funciones según el tipo de cuenta
    
    Args:
        user_id: ID del usuario
        
    Returns:
        dict: Diccionario con límites para diferentes funciones
    """
    if is_premium(user_id):
        return {
            'filtros_avanzados': True,
            'alertas_personalizadas': True,
            'sin_anuncios': True,
            'acceso_prioritario': True
        }
    else:
        return {
            'filtros_avanzados': False,
            'alertas_personalizadas': False,
            'sin_anuncios': False,
            'acceso_prioritario': False
        }


def check_favoritos_limit(user_id):
    """
    Verifica si un usuario puede añadir más oposiciones a favoritos
    Ahora todos los usuarios tienen favoritos ilimitados
    
    Args:
        user_id: ID del usuario
        
    Returns:
        tuple: (puede_añadir: bool, mensaje: str)
    """
    # Todos los usuarios pueden añadir favoritos sin límite
    return True, None
