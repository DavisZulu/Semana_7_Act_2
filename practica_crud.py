# practica_crud.py
# Quantum Core - Operaciones CRUD (Create, Read, Update, Delete) sobre la tabla
# contactos: la agenda profesional de cada usuario de la Quantum Wallet.
#
# Codigo original de la actividad (enunciado de Canvas y repositorio del curso,
# MisProyectosPython/Semana_7/practica_crud.py): tabla contactos vinculada al
# usuario por FK (id_contacto, apodo, numero, id_usuario) y una funcion por operacion:
#   C - insertar contactos para el usuario 1
#   R - mostrar en consola los contactos del usuario 1
#   U - cambiar el apodo de un contacto (con WHERE)
#   D - eliminar el contacto con id 2
# Todo eso se conserva. Para enriquecer el ejercicio se adicionaron los
# elementos marcados con  [AGREGADO]: atributos de una agenda profesional
# (nombre completo, categoria, empresa, ciudad, correo), validacion en dos capas,
# autorizacion por usuario, lista blanca de campos, busqueda, resumen por
# categoria, favoritos, transferencias a un contacto con cuenta en Quantum Wallet,
# registro (logging) y pruebas de seguridad.
#
# Requiere la base creada por configurar_db.py (misma carpeta).
# Ejecutar:            python3 practica_crud.py
# Con pausas para tomar capturas en DB Browser:  python3 practica_crud.py --pausas

import logging
import re
import sqlite3
import sys
from pathlib import Path

from configurar_db import RUTA_DB, conectar, transferir

RUTA_LOG = Path(__file__).with_name("crud_contactos.log")
PAUSAS = "--pausas" in sys.argv

# Categorias permitidas para clasificar la agenda.                     [AGREGADO]
CATEGORIAS = ("FAMILIA", "TRABAJO", "PROVEEDOR", "CLIENTE", "SERVICIO", "EMERGENCIA")

# Campos que el usuario puede modificar (lista blanca).                [AGREGADO]
# Ningun otro nombre de columna llega nunca a una sentencia SQL.
CAMPOS_EDITABLES = {"apodo", "nombre_completo", "categoria", "empresa", "numero",
                    "email", "ciudad", "favorito"}


# ======================================================================
# REGISTRO (logging): consola + archivo                                [AGREGADO]
# ======================================================================
def configurar_log():
    """Registra cada operacion en la consola y en crud_contactos.log (con fecha y hora)."""
    registro = logging.getLogger("crud_contactos")
    registro.setLevel(logging.INFO)
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(logging.Formatter("%(levelname)-7s | %(message)s"))
    archivo = logging.FileHandler(RUTA_LOG, mode="w", encoding="utf-8")
    archivo.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    registro.addHandler(consola)
    registro.addHandler(archivo)
    return registro


log = configurar_log()


# ======================================================================
# ESQUEMA: tabla contactos
# ======================================================================
ESQUEMA_CONTACTOS = """
DROP TABLE IF EXISTS contactos;

CREATE TABLE contactos (
    id_contacto          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario           INTEGER NOT NULL,            -- dueno de la agenda (FK)
    apodo                TEXT    NOT NULL COLLATE NOCASE
                         CONSTRAINT ck_contacto_apodo
                         CHECK (length(trim(apodo)) BETWEEN 1 AND 40),
    nombre_completo      TEXT    NOT NULL                                  -- [AGREGADO]
                         CONSTRAINT ck_contacto_nombre
                         CHECK (length(trim(nombre_completo)) BETWEEN 3 AND 80),
    categoria            TEXT    NOT NULL                                  -- [AGREGADO]
                         CONSTRAINT ck_contacto_categoria CHECK (categoria IN
                         ('FAMILIA', 'TRABAJO', 'PROVEEDOR', 'CLIENTE', 'SERVICIO', 'EMERGENCIA')),
    empresa              TEXT,                                             -- [AGREGADO]
    numero               TEXT    NOT NULL
                         CONSTRAINT ck_contacto_numero
                         CHECK (numero NOT GLOB '*[^0-9]*' AND length(numero) BETWEEN 3 AND 15),
    email                TEXT                                              -- [AGREGADO]
                         CONSTRAINT ck_contacto_email
                         CHECK (email IS NULL OR email LIKE '%_@_%._%'),
    ciudad               TEXT,                                             -- [AGREGADO]
    id_usuario_contacto  INTEGER,                                          -- [AGREGADO]
    favorito             INTEGER NOT NULL DEFAULT 0                        -- [AGREGADO]
                         CONSTRAINT ck_contacto_favorito CHECK (favorito IN (0, 1)),
    fecha_creacion       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')), -- [AGREGADO]
    fecha_actualizacion  TEXT,                                             -- [AGREGADO]
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    FOREIGN KEY (id_usuario_contacto) REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
    -- [AGREGADO] En una misma agenda no se repiten ni el numero ni el apodo
    CONSTRAINT uq_contacto_numero UNIQUE (id_usuario, numero),
    CONSTRAINT uq_contacto_apodo  UNIQUE (id_usuario, apodo),
    -- [AGREGADO] Un usuario no se agenda a si mismo
    CONSTRAINT ck_contacto_no_propio CHECK (id_usuario_contacto IS NULL
                                            OR id_usuario_contacto <> id_usuario)
);

CREATE INDEX idx_contactos_usuario ON contactos (id_usuario, categoria);   -- [AGREGADO]
"""


def crear_tabla_contactos(conexion):
    """Crea la tabla desde cero; al borrarla, SQLite reinicia su contador de ids."""
    conexion.executescript(ESQUEMA_CONTACTOS)
    log.info("Tabla contactos creada: 14 columnas, 2 FK, 7 CHECK, 2 UNIQUE y 1 indice")


# ======================================================================
# VALIDACION EN PYTHON (primera capa)                                  [AGREGADO]
# La base de datos repite estas reglas con CHECK y UNIQUE (segunda capa).
# ======================================================================
PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_texto(valor, campo, minimo, maximo, obligatorio=True):
    """Quita espacios y exige una longitud entre minimo y maximo; None si es opcional y vacio."""
    valor = (valor or "").strip()
    if not valor and not obligatorio:
        return None
    if not minimo <= len(valor) <= maximo:
        raise ValueError(f"{campo} debe tener entre {minimo} y {maximo} caracteres")
    return valor


def validar_apodo(apodo):
    """El apodo es obligatorio y tiene entre 1 y 40 caracteres."""
    return validar_texto(apodo, "el apodo", 1, 40)


def validar_nombre(nombre):
    """El nombre completo es obligatorio y tiene entre 3 y 80 caracteres."""
    return validar_texto(nombre, "el nombre completo", 3, 80)


def validar_categoria(categoria):
    """La categoria debe ser una de las seis permitidas; se normaliza a mayusculas."""
    categoria = (categoria or "").strip().upper()
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria no valida '{categoria}': use {', '.join(CATEGORIAS)}")
    return categoria


def validar_numero(numero):
    """El numero solo admite digitos, entre 3 (lineas cortas) y 15 (maximo internacional)."""
    numero = str(numero or "").strip()
    if not numero.isdigit() or not 3 <= len(numero) <= 15:
        raise ValueError(f"numero no valido '{numero}': solo digitos, entre 3 y 15")
    return numero


def validar_email(email):
    """El correo es opcional; si se indica, debe tener el formato usuario@dominio.ext."""
    if email in (None, ""):
        return None
    if not PATRON_EMAIL.match(email):
        raise ValueError(f"correo no valido: {email}")
    return email


def validar_id(valor, nombre="id"):
    """Los identificadores deben ser enteros: evita que un texto llegue al WHERE."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(f"{nombre} debe ser un numero entero: {valor!r}")
    return valor


VALIDADORES = {
    "apodo": validar_apodo,
    "nombre_completo": validar_nombre,
    "categoria": validar_categoria,
    "empresa": lambda v: validar_texto(v, "la empresa", 2, 60, obligatorio=False),
    "numero": validar_numero,
    "email": validar_email,
    "ciudad": lambda v: validar_texto(v, "la ciudad", 2, 40, obligatorio=False),
    "favorito": lambda v: 1 if v else 0,
}


# ======================================================================
# C - CREATE
# ======================================================================
def crear_contactos(conexion, id_usuario, contactos):
    """C - CREATE: inserta una lista de contactos en la agenda de un usuario.

    Todas las filas se validan antes de insertar y se guardan en una sola
    transaccion (executemany): o entran todas o no entra ninguna.
    """
    validar_id(id_usuario, "id_usuario")
    filas = [
        (id_usuario, validar_apodo(c["apodo"]), validar_nombre(c["nombre_completo"]),
         validar_categoria(c["categoria"]), VALIDADORES["empresa"](c.get("empresa")),
         validar_numero(c["numero"]), validar_email(c.get("email")),
         VALIDADORES["ciudad"](c.get("ciudad")), c.get("id_usuario_contacto"))
        for c in contactos
    ]
    with conexion:
        conexion.executemany(
            "INSERT INTO contactos (id_usuario, apodo, nombre_completo, categoria, empresa, "
            "numero, email, ciudad, id_usuario_contacto) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
            filas,
        )
    log.info("C - Create: %d %s para el usuario %d", len(filas),
             "contacto insertado" if len(filas) == 1 else "contactos insertados", id_usuario)


# ======================================================================
# R - READ
# ======================================================================
def leer_contactos(conexion, id_usuario, categoria=None):
    """R - READ: devuelve y muestra en consola la agenda de un usuario.

    Opcionalmente filtra por categoria. El LEFT JOIN agrega el nombre del
    contacto en Quantum Wallet cuando tiene cuenta.
    """
    sql = """
        SELECT c.id_contacto, c.apodo, c.nombre_completo, c.categoria, c.numero,
               coalesce(c.ciudad, '-'), c.favorito, coalesce(u.nombre, '-')
        FROM contactos c
        LEFT JOIN usuarios u ON u.id_usuario = c.id_usuario_contacto
        WHERE c.id_usuario = ?
    """
    parametros = [id_usuario]
    if categoria:                                                        # [AGREGADO]
        sql += " AND c.categoria = ?"
        parametros.append(validar_categoria(categoria))
    filas = conexion.execute(sql + " ORDER BY c.id_contacto;", parametros).fetchall()

    filtro = f" (categoria {categoria})" if categoria else ""
    log.info("R - Read: %d contactos del usuario %s%s", len(filas), id_usuario, filtro)
    if filas:
        log.info("     %3s  %-25s %-30s %-10s %-11s %-20s %s",
                 "id", "apodo", "nombre completo", "categoria", "numero", "ciudad", "cuenta Quantum")
    for id_contacto, apodo, nombre, cat, numero, ciudad, favorito, cuenta in filas:
        estrella = "*" if favorito else " "
        log.info("   %s %3d  %-25s %-30s %-10s %-11s %-20s %s",
                 estrella, id_contacto, apodo, nombre, cat, numero, ciudad, cuenta)
    return filas


def resumen_por_categoria(conexion, id_usuario):                                # [AGREGADO]
    """Cuenta los contactos de la agenda por categoria (GROUP BY)."""
    filas = conexion.execute(
        "SELECT categoria, count(*) FROM contactos WHERE id_usuario = ? "
        "GROUP BY categoria ORDER BY count(*) DESC, categoria;",
        (id_usuario,),
    ).fetchall()
    log.info("Resumen de la agenda del usuario %d por categoria: %s", id_usuario,
             ", ".join(f"{categoria} {cantidad}" for categoria, cantidad in filas))
    return filas


# ======================================================================
# U - UPDATE
# ======================================================================
def actualizar_apodo(conexion, id_usuario, id_contacto, nuevo_apodo):
    """U - UPDATE: cambia el apodo de UN contacto.

    El WHERE usa la llave primaria y el dueno de la agenda: solo se modifica esa
    fila, y un usuario no puede cambiar contactos de otro.
    """
    validar_id(id_contacto, "id_contacto")
    nuevo_apodo = validar_apodo(nuevo_apodo)
    with conexion:
        anterior = conexion.execute(
            "SELECT apodo FROM contactos WHERE id_contacto = ? AND id_usuario = ?;",
            (id_contacto, id_usuario),
        ).fetchone()
        cursor = conexion.execute(
            "UPDATE contactos SET apodo = ?, fecha_actualizacion = datetime('now', 'localtime') "
            "WHERE id_contacto = ? AND id_usuario = ?;",
            (nuevo_apodo, id_contacto, id_usuario),
        )
        if cursor.rowcount == 0:
            raise LookupError(f"el contacto {id_contacto} no existe en la agenda del usuario {id_usuario}")
    log.info("U - Update: contacto %d '%s' -> '%s' (%d fila modificada)",
             id_contacto, anterior[0], nuevo_apodo, cursor.rowcount)


def actualizar_contacto(conexion, id_usuario, id_contacto, /, **cambios):       # [AGREGADO]
    """Actualiza varios campos a la vez, solo si estan en la lista blanca.

    La barra (/) obliga a pasar los tres primeros datos por posicion; asi, un
    intento como id_usuario=4 llega a **cambios y la lista blanca lo rechaza.
    """
    validar_id(id_contacto, "id_contacto")
    no_permitidos = set(cambios) - CAMPOS_EDITABLES
    if not cambios or no_permitidos:
        raise ValueError(f"campos no permitidos: {sorted(no_permitidos) or 'ninguno indicado'}")
    valores = {campo: VALIDADORES[campo](valor) for campo, valor in cambios.items()}
    # Los nombres de columna salen de la lista blanca; los valores van como parametros ?
    asignaciones = ", ".join(f"{campo} = ?" for campo in valores)
    with conexion:
        cursor = conexion.execute(
            f"UPDATE contactos SET {asignaciones}, fecha_actualizacion = datetime('now', 'localtime') "
            "WHERE id_contacto = ? AND id_usuario = ?;",
            (*valores.values(), id_contacto, id_usuario),
        )
        if cursor.rowcount == 0:
            raise LookupError(f"el contacto {id_contacto} no existe en la agenda del usuario {id_usuario}")
    log.info("U - Update: contacto %d actualizado %s", id_contacto, valores)


# ======================================================================
# D - DELETE
# ======================================================================
def borrar_contacto(conexion, id_usuario, id_contacto):
    """D - DELETE: elimina UN contacto por su id (una fila, nunca la tabla)."""
    validar_id(id_contacto, "id_contacto")
    with conexion:
        fila = conexion.execute(
            "SELECT apodo, nombre_completo, numero FROM contactos "
            "WHERE id_contacto = ? AND id_usuario = ?;",
            (id_contacto, id_usuario),
        ).fetchone()
        if fila is None:
            raise LookupError(f"el contacto {id_contacto} no existe en la agenda del usuario {id_usuario}")
        cursor = conexion.execute(
            "DELETE FROM contactos WHERE id_contacto = ? AND id_usuario = ?;",
            (id_contacto, id_usuario),
        )
    log.info("D - Delete: contacto %d '%s' (%s, %s) eliminado (%d fila)",
             id_contacto, fila[0], fila[1], fila[2], cursor.rowcount)


# ======================================================================
# FUNCIONALIDADES ADICIONALES                                          [AGREGADO]
# ======================================================================
def buscar_contactos(conexion, id_usuario, texto):
    """Busca por apodo, nombre, empresa o numero. Los comodines % y _ se escapan."""
    patron = "%" + texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    filas = conexion.execute(
        "SELECT id_contacto, apodo FROM contactos WHERE id_usuario = ? AND ("
        "apodo LIKE ? ESCAPE '\\' OR nombre_completo LIKE ? ESCAPE '\\' OR "
        "empresa LIKE ? ESCAPE '\\' OR numero LIKE ? ESCAPE '\\') ORDER BY apodo;",
        (id_usuario, patron, patron, patron, patron),
    ).fetchall()
    log.info("Busqueda '%s' en la agenda del usuario %s: %d resultado(s) %s",
             texto, id_usuario, len(filas), [f[1] for f in filas])
    return filas


def transferir_a_contacto(conexion, id_usuario, apodo, monto, descripcion="Transferencia a contacto"):
    """Integracion con Quantum Core: transfiere dinero a un contacto por su apodo.

    El contacto debe tener cuenta en Quantum Wallet (id_usuario_contacto). La
    operacion la ejecuta transferir() de configurar_db.py, con todas sus reglas.
    """
    fila = conexion.execute(
        "SELECT id_usuario_contacto FROM contactos WHERE id_usuario = ? AND apodo = ?;",
        (id_usuario, apodo),
    ).fetchone()
    if fila is None:
        raise LookupError(f"'{apodo}' no esta en la agenda del usuario {id_usuario}")
    if fila[0] is None:
        raise ValueError(f"el contacto '{apodo}' no tiene cuenta en Quantum Wallet")
    transferir(conexion, id_usuario, fila[0], monto, f"{descripcion} ({apodo})")
    log.info("Transferencia de %s a '%s' registrada en Quantum Core", f"{monto:,.2f}", apodo)


def saldo(conexion, id_usuario):
    """Devuelve el saldo actual de la wallet del usuario."""
    return conexion.execute(
        "SELECT saldo FROM wallets WHERE id_propietario = ?;", (id_usuario,)
    ).fetchone()[0]


# ======================================================================
# PRUEBAS DE SEGURIDAD Y VALIDACION                                    [AGREGADO]
# ======================================================================
def nuevo(apodo, numero, **extra):
    """Contacto minimo para las pruebas."""
    return [{"apodo": apodo, "nombre_completo": extra.pop("nombre", "Contacto de prueba"),
             "categoria": extra.pop("categoria", "SERVICIO"), "numero": numero, **extra}]


def probar_seguridad(conexion):
    """Prueba la inyeccion SQL y 13 operaciones invalidas; todas deben ser rechazadas."""
    log.info("Inyeccion SQL en la lectura: leer_contactos(conexion, '1 OR 1=1')")
    filas = leer_contactos(conexion, "1 OR 1=1")
    log.info("    -> %d filas: el texto se trato como un valor, no como codigo SQL", len(filas))
    filas = buscar_contactos(conexion, 1, "' OR '1'='1")
    log.info("    -> la busqueda con comillas devolvio %d filas", len(filas))

    pruebas = [
        ("Numero con letras", lambda: crear_contactos(conexion, 1, nuevo("Banco", "300-ABC"))),
        ("Apodo vacio", lambda: crear_contactos(conexion, 1, nuevo("  ", "3001234567"))),
        ("Categoria no permitida", lambda: crear_contactos(conexion, 1, nuevo("Vecino", "3001234568", categoria="AMIGO"))),
        ("Nombre completo demasiado corto", lambda: crear_contactos(conexion, 1, nuevo("Socio", "3001234569", nombre="Al"))),
        ("Numero repetido en la agenda", lambda: crear_contactos(conexion, 1, nuevo("Contador 2", "3104458721"))),
        ("Apodo repetido (sin importar mayusculas)", lambda: crear_contactos(conexion, 1, nuevo("CONTADOR Y REVISOR FISCAL", "3009990000"))),
        ("Contacto para un usuario inexistente", lambda: crear_contactos(conexion, 999, nuevo("Nadie", "3000000000"))),
        ("Agendarse a si mismo", lambda: crear_contactos(conexion, 1, nuevo("Yo", "3000000001", id_usuario_contacto=1))),
        ("Modificar un contacto de otro usuario", lambda: actualizar_apodo(conexion, 1, 11, "Modificado")),
        ("Borrar un contacto que ya no existe", lambda: borrar_contacto(conexion, 1, 2)),
        ("Actualizar un campo fuera de la lista blanca", lambda: actualizar_contacto(conexion, 1, 1, id_usuario=4)),
        ("SQL directo que evita la validacion de Python", lambda: conexion.execute(
            "INSERT INTO contactos (id_usuario, apodo, nombre_completo, categoria, numero) "
            "VALUES (1, 'Directo', 'Insercion directa', 'OTRA', 'abc');")),
        ("Transferir a un contacto sin cuenta Quantum", lambda: transferir_a_contacto(conexion, 1, "Contador y revisor fiscal", 10000)),
    ]
    rechazadas = 0
    for descripcion, operacion in pruebas:
        try:
            operacion()
            conexion.commit()
            log.error("ACEPTADA  %s", descripcion)
        except (sqlite3.DatabaseError, ValueError, LookupError) as error:
            conexion.rollback()
            rechazadas += 1
            log.warning("RECHAZADA %s -> %s: %s", descripcion, type(error).__name__, error)
    log.info("Resultado: %d de %d operaciones invalidas rechazadas", rechazadas, len(pruebas))


# ======================================================================
# DATOS DE LA AGENDA
# ======================================================================
AGENDA_USUARIO_1 = [   # Ana Torres: agenda profesional de 10 contactos
    {"apodo": "Contador", "nombre_completo": "Andrés Felipe Restrepo Ospina", "categoria": "PROVEEDOR",
     "empresa": "Restrepo Contadores Asociados", "numero": "3104458721",
     "email": "arestrepo@restrepocontadores.co", "ciudad": "Medellín"},
    {"apodo": "Antiguo arrendador", "nombre_completo": "Jorge Iván Cardona Ruiz", "categoria": "SERVICIO",
     "empresa": "Inmobiliaria Los Andes", "numero": "6045612233", "ciudad": "Rionegro"},
    {"apodo": "Jefe inmediato", "nombre_completo": "Mariana Velásquez Henao", "categoria": "TRABAJO",
     "empresa": "Quantum SAS", "numero": "3157723410", "email": "mvelasquez@quantum.com",
     "ciudad": "Medellín"},
    {"apodo": "Laura - Desarrollo", "nombre_completo": "Laura Gomez", "categoria": "TRABAJO",
     "empresa": "Quantum SAS", "numero": "3104567890", "email": "laura.gomez@quantum.com",
     "ciudad": "Medellín", "id_usuario_contacto": 4},
    {"apodo": "Pedro - Analista", "nombre_completo": "Pedro Rios", "categoria": "TRABAJO",
     "empresa": "Quantum SAS", "numero": "3126665544", "ciudad": "Medellín", "id_usuario_contacto": 5},
    {"apodo": "Cliente principal", "nombre_completo": "Catalina Zuluaga Montoya", "categoria": "CLIENTE",
     "empresa": "Cerámicas Viboral SAS", "numero": "3005582214", "email": "compras@ceramicasviboral.co",
     "ciudad": "El Carmen de Viboral"},
    {"apodo": "Soporte de software", "nombre_completo": "Nicolás Ramírez Echeverri", "categoria": "PROVEEDOR",
     "empresa": "TecnoRetiro SAS", "numero": "3126654098", "email": "soporte@tecnoretiro.co",
     "ciudad": "El Retiro"},
    {"apodo": "Asesora jurídica", "nombre_completo": "Daniela Ospina Giraldo", "categoria": "PROVEEDOR",
     "empresa": "Ospina & Asociados", "numero": "3187742001", "email": "dospina@ospinaabogados.co",
     "ciudad": "Medellín"},
    {"apodo": "Hermano", "nombre_completo": "Santiago Torres Arango", "categoria": "FAMILIA",
     "numero": "3014456677", "ciudad": "La Ceja"},
    {"apodo": "Línea de emergencias", "nombre_completo": "Línea Única de Emergencias", "categoria": "EMERGENCIA",
     "numero": "123", "ciudad": "Nacional"},
]


# ======================================================================
# PROGRAMA PRINCIPAL
# ======================================================================
def titulo(texto):
    """Imprime el separador de cada etapa en la consola."""
    print(f"\n--- {texto} " + "-" * max(0, 80 - len(texto)))


def pausa(mensaje):
    """Con --pausas, detiene la ejecucion para tomar la captura en DB Browser."""
    if PAUSAS:
        input(f"\n>>> {mensaje}\n>>> Presione Enter para continuar...")


if __name__ == "__main__":
    print("=" * 86)
    print(" QUANTUM CORE - Operaciones CRUD sobre la agenda de contactos")
    print("=" * 86)
    if not RUTA_DB.exists():
        raise SystemExit("No existe quantum_wallet.db: ejecute primero  python3 configurar_db.py")

    conexion = conectar()            # PRAGMA foreign_keys = ON
    crear_tabla_contactos(conexion)

    titulo("C - CREATE")
    crear_contactos(conexion, 1, AGENDA_USUARIO_1)
    # [AGREGADO] Agendas de otros usuarios, para comprobar que cada uno ve solo la suya
    crear_contactos(conexion, 4, [{"apodo": "Ana - Finanzas", "nombre_completo": "Ana Torres",
                                   "categoria": "TRABAJO", "empresa": "Quantum SAS",
                                   "numero": "3157778899", "id_usuario_contacto": 1}])
    crear_contactos(conexion, 3, [{"apodo": "Pedro Rios - Nómina", "nombre_completo": "Pedro Rios",
                                   "categoria": "TRABAJO", "numero": "3126665544",
                                   "id_usuario_contacto": 5}])
    pausa("Captura C: en DB Browser abra la tabla contactos (Browse Data, Refresh).")

    titulo("R - READ")
    leer_contactos(conexion, 1)
    resumen_por_categoria(conexion, 1)                                   # [AGREGADO]
    leer_contactos(conexion, 1, categoria="PROVEEDOR")                   # [AGREGADO]

    titulo("U - UPDATE")
    actualizar_apodo(conexion, 1, 1, "Contador y revisor fiscal")
    actualizar_contacto(conexion, 1, 7, numero="3126654099",             # [AGREGADO]
                        email="mesadeayuda@tecnoretiro.co")
    actualizar_contacto(conexion, 1, 4, favorito=True)                   # [AGREGADO]
    pausa("Captura U: actualice DB Browser (Refresh) y revise los contactos 1, 4 y 7.")

    titulo("D - DELETE")
    borrar_contacto(conexion, 1, 2)
    pausa("Captura D: actualice DB Browser (Refresh): el contacto 2 ya no esta.")

    titulo("BUSQUEDA [AGREGADO]")
    buscar_contactos(conexion, 1, "Quantum")

    titulo("INTEGRACION CON QUANTUM CORE [AGREGADO]")
    antes = (saldo(conexion, 1), saldo(conexion, 4))
    transferir_a_contacto(conexion, 1, "Laura - Desarrollo", 150000.00, "Reembolso de gastos de viaje")
    log.info("Saldo de Ana Torres  : %15s -> %15s", f"{antes[0]:,.2f}", f"{saldo(conexion, 1):,.2f}")
    log.info("Saldo de Laura Gomez : %15s -> %15s", f"{antes[1]:,.2f}", f"{saldo(conexion, 4):,.2f}")

    titulo("SEGURIDAD Y VALIDACION [AGREGADO]")
    probar_seguridad(conexion)

    titulo("ESTADO FINAL")
    leer_contactos(conexion, 1)
    resumen_por_categoria(conexion, 1)

    conexion.close()
    print(f"\nRegistro completo en {RUTA_LOG.name}")
