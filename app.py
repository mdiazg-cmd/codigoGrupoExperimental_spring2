# Plataforma de solicitudes de soporte - Grupo 5 - Sprint 1
import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, abort)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "clave-de-prueba-grupo5"
app.config["DB"] = "soporte.db"

CATEGORIAS = ["Hardware", "Software", "Red", "Accesos", "Otro"]
PRIORIDADES = ["Baja", "Media", "Alta"]
# transiciones que puede hacer el agente (HU07)
AGENTE_PUEDE = [("Asignada", "En atención"), ("En atención", "Resuelta"),
                ("Reabierta", "En atención")]
ORDENES = {
    "prioridad": "CASE s.prioridad WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 "
                 "WHEN 'Baja' THEN 3 ELSE 4 END",
    "estado": "s.estado",
    "fecha": "s.fecha DESC",
}


# ---------- base de datos ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def cerrar_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(app.config["DB"])
    db.executescript("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        clave_hash TEXT NOT NULL,
        rol TEXT NOT NULL,
        activo INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS solicitudes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        categoria TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'Nuevo',
        prioridad TEXT NOT NULL DEFAULT 'Sin definir',
        propietario_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        actualizada TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitud_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        campo TEXT NOT NULL,
        valor_anterior TEXT,
        valor_nuevo TEXT,
        fecha TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS comentarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitud_id INTEGER NOT NULL,
        autor_id INTEGER NOT NULL,
        texto TEXT NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'trabajo',
        fecha TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS notificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        mensaje TEXT NOT NULL,
        fecha TEXT NOT NULL
    );
    CREATE TRIGGER IF NOT EXISTS comentarios_no_update BEFORE UPDATE ON comentarios
        BEGIN SELECT RAISE(ABORT, 'Los comentarios no se pueden editar'); END;
    CREATE TRIGGER IF NOT EXISTS comentarios_no_delete BEFORE DELETE ON comentarios
        BEGIN SELECT RAISE(ABORT, 'Los comentarios no se pueden borrar'); END;
    CREATE TRIGGER IF NOT EXISTS historial_no_update BEFORE UPDATE ON historial
        BEGIN SELECT RAISE(ABORT, 'El historial no se puede modificar'); END;
    CREATE TRIGGER IF NOT EXISTS historial_no_delete BEFORE DELETE ON historial
        BEGIN SELECT RAISE(ABORT, 'El historial no se puede borrar'); END;
    """)
    # columnas nuevas (si la base viene del sprint 1)
    for col in ("agente_id INTEGER", "justificacion TEXT", "fecha_objetivo TEXT"):
        try:
            db.execute("ALTER TABLE solicitudes ADD COLUMN " + col)
        except sqlite3.OperationalError:
            pass
    # datos semilla (ficticios)
    semilla = [("solicitante1", "solicitante", 1), ("solicitante2", "solicitante", 1),
               ("agente1", "agente", 1), ("agente2", "agente", 1),
               ("agente3", "agente", 0),  # agente inactivo (para probar HU05)
               ("coord1", "coordinador", 1), ("auditor1", "auditor", 1)]
    for usuario, rol, activo in semilla:
        db.execute("INSERT OR IGNORE INTO usuarios (usuario, clave_hash, rol, activo) VALUES (?,?,?,?)",
                   (usuario, generate_password_hash("Clave123*"), rol, activo))
    db.commit()
    db.close()


def codigo(uid):
    return "U%03d" % uid


def registrar(db, sid, campo, anterior, nuevo):
    """Guarda un evento en el historial (quién, cuándo, qué cambió)."""
    db.execute("INSERT INTO historial (solicitud_id, usuario_id, campo, valor_anterior, valor_nuevo, fecha) "
               "VALUES (?,?,?,?,?,?)", (sid, session["usuario_id"], campo, anterior, nuevo, ahora()))


def fecha_valida(texto):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date() >= datetime.now().date()
    except ValueError:
        return False


def cargar(id):
    """Trae la solicitud si el rol actual puede verla; si no, 404."""
    s = get_db().execute(
        "SELECT s.*, u.usuario, a.usuario AS agente FROM solicitudes s "
        "JOIN usuarios u ON u.id = s.propietario_id "
        "LEFT JOIN usuarios a ON a.id = s.agente_id WHERE s.id = ?", (id,)).fetchone()
    if s is None:
        abort(404)
    if session["rol"] == "solicitante" and s["propietario_id"] != session["usuario_id"]:
        abort(404)
    if session["rol"] == "agente" and s["agente_id"] != session["usuario_id"]:
        abort(404)
    return s


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- control de acceso ----------
def login_requerido(*roles):
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if "usuario_id" not in session:
                return redirect(url_for("login"))
            if roles and session["rol"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return envoltura
    return decorador


# ---------- HU01: sesión ----------
@app.route("/")
def index():
    return redirect(url_for("inicio"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        clave = request.form.get("clave", "")
        u = get_db().execute("SELECT * FROM usuarios WHERE usuario = ? AND activo = 1",
                             (usuario,)).fetchone()
        # mismo mensaje si el usuario no existe o la clave está mal
        if u is None or not check_password_hash(u["clave_hash"], clave):
            flash("Usuario o contraseña incorrectos")
            return render_template("login.html"), 401
        session.clear()
        session["usuario_id"] = u["id"]
        session["usuario"] = u["usuario"]
        session["rol"] = u["rol"]
        return redirect(url_for("inicio"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/inicio")
@login_requerido()
def inicio():
    notis = get_db().execute("SELECT * FROM notificaciones WHERE usuario_id = ? ORDER BY id DESC LIMIT 5",
                             (session["usuario_id"],)).fetchall()
    return render_template("inicio.html", notis=notis)


# ---------- HU02: crear solicitud ----------
@app.route("/solicitudes/nueva", methods=["GET", "POST"])
@login_requerido("solicitante")
def nueva():
    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        categoria = request.form.get("categoria", "")
        if not titulo or not descripcion or categoria not in CATEGORIAS:
            flash("Título, descripción y categoría son obligatorios")
            return render_template("nueva.html", categorias=CATEGORIAS), 400
        f = ahora()
        db = get_db()
        cur = db.execute(
            "INSERT INTO solicitudes (titulo, descripcion, categoria, propietario_id, fecha, actualizada) "
            "VALUES (?,?,?,?,?,?)",
            (titulo, descripcion, categoria, session["usuario_id"], f, f))
        db.commit()
        flash("Solicitud creada con ID %d" % cur.lastrowid)
        return redirect(url_for("detalle", id=cur.lastrowid))
    return render_template("nueva.html", categorias=CATEGORIAS)


# ---------- HU03 y HU04: listar ----------
BASE_SQL = ("SELECT s.*, u.usuario, a.usuario AS agente FROM solicitudes s "
            "JOIN usuarios u ON u.id = s.propietario_id "
            "LEFT JOIN usuarios a ON a.id = s.agente_id")


@app.route("/solicitudes")
@login_requerido("solicitante", "agente", "coordinador")
def lista():
    orden = request.args.get("orden", "fecha")
    if orden not in ORDENES:
        orden = "fecha"
    donde, params = "", []
    if session["rol"] == "solicitante":
        donde, params = " WHERE s.propietario_id = ?", [session["usuario_id"]]
    elif session["rol"] == "agente":
        donde, params = " WHERE s.agente_id = ?", [session["usuario_id"]]
    filas = get_db().execute(BASE_SQL + donde + " ORDER BY " + ORDENES[orden], params).fetchall()
    return render_template("lista.html", filas=filas, orden=orden)


@app.route("/solicitudes/<int:id>")
@login_requerido("solicitante", "agente", "coordinador")
def detalle(id):
    s = cargar(id)
    db = get_db()
    hist = db.execute("SELECT h.*, u.usuario FROM historial h JOIN usuarios u ON u.id = h.usuario_id "
                      "WHERE h.solicitud_id = ? ORDER BY h.id", (id,)).fetchall()
    coments = db.execute("SELECT c.*, u.usuario FROM comentarios c JOIN usuarios u ON u.id = c.autor_id "
                         "WHERE c.solicitud_id = ? ORDER BY c.id", (id,)).fetchall()
    agentes = db.execute("SELECT id, usuario FROM usuarios WHERE rol = 'agente' AND activo = 1").fetchall()
    siguientes = [n for (a, n) in AGENTE_PUEDE if a == s["estado"]]
    return render_template("detalle.html", s=s, hist=hist, coments=coments, agentes=agentes,
                           siguientes=siguientes, prioridades=PRIORIDADES)


# ---------- HU04 (adaptado): prioridad Alta pide justificación y fecha objetivo ----------
@app.route("/solicitudes/<int:id>/prioridad", methods=["POST"])
@login_requerido("coordinador")
def priorizar(id):
    s = cargar(id)
    nueva_p = request.form.get("prioridad", "")
    if nueva_p not in PRIORIDADES:
        flash("Prioridad no válida")
        return redirect(url_for("detalle", id=id))
    just = request.form.get("justificacion", "").strip()
    fobj = request.form.get("fecha_objetivo", "").strip()
    if nueva_p == "Alta" and (not just or not fecha_valida(fobj)):
        flash("La prioridad Alta requiere justificación y una fecha objetivo válida (AAAA-MM-DD)")
        return redirect(url_for("detalle", id=id))
    if nueva_p != s["prioridad"]:
        db = get_db()
        db.execute("UPDATE solicitudes SET prioridad = ?, justificacion = ?, fecha_objetivo = ?, actualizada = ? "
                   "WHERE id = ?",
                   (nueva_p, just if nueva_p == "Alta" else None,
                    fobj if nueva_p == "Alta" else None, ahora(), id))
        registrar(db, id, "prioridad", s["prioridad"], nueva_p)
        db.commit()
        flash("Prioridad actualizada")
    return redirect(url_for("detalle", id=id))


# ---------- HU05: asignar ----------
@app.route("/solicitudes/<int:id>/asignar", methods=["POST"])
@login_requerido("coordinador")
def asignar(id):
    s = cargar(id)
    db = get_db()
    try:
        aid = int(request.form.get("agente_id", ""))
    except ValueError:
        aid = None
    ag = db.execute("SELECT * FROM usuarios WHERE id = ? AND rol = 'agente' AND activo = 1",
                    (aid,)).fetchone()
    if ag is None or s["estado"] == "Cerrada":
        flash("Asignación no válida: el agente debe estar activo y la solicitud no puede estar cerrada")
        return redirect(url_for("detalle", id=id))
    anterior = codigo(s["agente_id"]) if s["agente_id"] else None
    db.execute("UPDATE solicitudes SET agente_id = ?, actualizada = ? WHERE id = ?", (aid, ahora(), id))
    registrar(db, id, "asignación", anterior, codigo(aid))
    if s["estado"] == "Nuevo":
        db.execute("UPDATE solicitudes SET estado = 'Asignada' WHERE id = ?", (id,))
        registrar(db, id, "estado", "Nuevo", "Asignada")
    db.execute("INSERT INTO notificaciones (usuario_id, mensaje, fecha) VALUES (?,?,?)",
               (aid, "Se te asignó la solicitud #%d" % id, ahora()))
    db.commit()
    flash("Solicitud asignada a " + ag["usuario"])
    return redirect(url_for("detalle", id=id))


# ---------- HU06: comentarios ----------
@app.route("/solicitudes/<int:id>/comentar", methods=["POST"])
@login_requerido("agente")
def comentar(id):
    cargar(id)  # solo el agente asignado llega hasta aquí
    texto = request.form.get("texto", "").strip()
    if not texto:
        flash("El comentario no puede estar vacío")
        return redirect(url_for("detalle", id=id))
    db = get_db()
    cur = db.execute("INSERT INTO comentarios (solicitud_id, autor_id, texto, tipo, fecha) VALUES (?,?,?,?,?)",
                     (id, session["usuario_id"], texto, "trabajo", ahora()))
    db.execute("UPDATE solicitudes SET actualizada = ? WHERE id = ?", (ahora(), id))
    registrar(db, id, "comentario", None, "C%d" % cur.lastrowid)
    db.commit()
    return redirect(url_for("detalle", id=id))


# ---------- HU07: cambiar estado ----------
@app.route("/solicitudes/<int:id>/estado", methods=["POST"])
@login_requerido("agente")
def cambiar_estado(id):
    s = cargar(id)
    nuevo = request.form.get("estado", "")
    if (s["estado"], nuevo) not in AGENTE_PUEDE:
        flash("Transición no permitida: %s -> %s" % (s["estado"], nuevo))
        return redirect(url_for("detalle", id=id))
    db = get_db()
    db.execute("UPDATE solicitudes SET estado = ?, actualizada = ? WHERE id = ?", (nuevo, ahora(), id))
    registrar(db, id, "estado", s["estado"], nuevo)
    db.commit()
    return redirect(url_for("detalle", id=id))


# ---------- HU08: confirmar o reabrir ----------
@app.route("/solicitudes/<int:id>/confirmar", methods=["POST"])
@login_requerido("solicitante")
def confirmar(id):
    s = cargar(id)
    if s["estado"] != "Resuelta":
        flash("Solo se puede confirmar una solicitud Resuelta")
        return redirect(url_for("detalle", id=id))
    db = get_db()
    db.execute("UPDATE solicitudes SET estado = 'Cerrada', actualizada = ? WHERE id = ?", (ahora(), id))
    registrar(db, id, "confirmación", "Resuelta", "Cerrada")
    db.commit()
    flash("Solicitud cerrada")
    return redirect(url_for("detalle", id=id))


@app.route("/solicitudes/<int:id>/reabrir", methods=["POST"])
@login_requerido("solicitante")
def reabrir(id):
    s = cargar(id)
    motivo = request.form.get("motivo", "").strip()
    if s["estado"] != "Resuelta" or not motivo:
        flash("Para reabrir la solicitud debe estar Resuelta y debes escribir un motivo")
        return redirect(url_for("detalle", id=id))
    db = get_db()
    db.execute("UPDATE solicitudes SET estado = 'Reabierta', actualizada = ? WHERE id = ?", (ahora(), id))
    db.execute("INSERT INTO comentarios (solicitud_id, autor_id, texto, tipo, fecha) VALUES (?,?,?,?,?)",
               (id, session["usuario_id"], motivo, "reapertura", ahora()))
    registrar(db, id, "reapertura", "Resuelta", "Reabierta")
    if s["agente_id"]:
        db.execute("INSERT INTO notificaciones (usuario_id, mensaje, fecha) VALUES (?,?,?)",
                   (s["agente_id"], "La solicitud #%d fue reabierta" % id, ahora()))
    db.commit()
    flash("Solicitud reabierta")
    return redirect(url_for("detalle", id=id))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
