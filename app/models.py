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
        genero,
        telefono=None,
        foto_perfil=None,
        dni=None,
        fecha_nacimiento=None,
        nacionalidad=None,
        direccion=None,
        codigo_postal=None,
        ciudad=None,
        provincia=None,
        nivel_estudios=None,
        titulacion=None,
        situacion_laboral=None,
        idiomas=None,
        discapacidad=None,
        porcentaje_discapacidad=None,
    ):
        self.id = id
        self.email = email
        self.name = name
        self.apellidos = apellidos
        self.age = age
        self.genero = genero
        self.telefono = telefono
        self.foto_perfil = foto_perfil
        self.dni = dni
        self.fecha_nacimiento = fecha_nacimiento
        self.nacionalidad = nacionalidad
        self.direccion = direccion
        self.codigo_postal = codigo_postal
        self.ciudad = ciudad
        self.provincia = provincia
        self.nivel_estudios = nivel_estudios
        self.titulacion = titulacion
        self.situacion_laboral = situacion_laboral
        self.idiomas = idiomas
        self.discapacidad = discapacidad
        self.porcentaje_discapacidad = porcentaje_discapacidad

    @staticmethod
    def get(user_id):
        db = get_users_db()
        row = db.execute(
            """
            SELECT id, email, name, apellidos, age, genero, telefono, foto_perfil,
                   dni, fecha_nacimiento, nacionalidad, direccion, codigo_postal,
                   ciudad, provincia, nivel_estudios, titulacion, situacion_laboral,
                   idiomas, discapacidad, porcentaje_discapacidad
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
                row["genero"],
                row["telefono"],
                row["foto_perfil"],
                row["dni"],
                row["fecha_nacimiento"],
                row["nacionalidad"],
                row["direccion"],
                row["codigo_postal"],
                row["ciudad"],
                row["provincia"],
                row["nivel_estudios"],
                row["titulacion"],
                row["situacion_laboral"],
                row["idiomas"],
                row["discapacidad"],
                row["porcentaje_discapacidad"],
            )
        return None


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)
