from flask_login import UserMixin
from . import login_manager
from .db import get_users_db


class User(UserMixin):
    def __init__(
        self,
        id,
        email,
        name,
        apellidos,
        age,
        telefono=None,
        foto_perfil=None,
        nivel_estudios=None,
        titulacion=None,
    ):
        self.id = id
        self.email = email
        self.name = name
        self.apellidos = apellidos
        self.age = age
        self.telefono = telefono
        self.foto_perfil = foto_perfil
        self.nivel_estudios = nivel_estudios
        self.titulacion = titulacion

    @staticmethod
    def get(user_id):
        db = get_users_db()
        row = db.execute(
            """
            SELECT id, email, name, apellidos, age, telefono, foto_perfil,
                nivel_estudios, titulacion
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if row:
            return User(
                row["id"],
                row["email"],
                row["name"],
                row["apellidos"],
                row["age"],
                row["telefono"],
                row["foto_perfil"],
                row["nivel_estudios"],
                row["titulacion"],
            )
        return None


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)
