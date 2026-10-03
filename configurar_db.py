# configurar_db.py
# Semana 7 - Quantum Core: persistencia de la Quantum Wallet con SQLite.
#
# Traduce a un esquema relacional el modelo de clases de usuarios.py
# (Semana 6) y genera la base de datos quantum_wallet.db.
#
# Codigo original de la actividad (enunciado de Canvas y repositorio del curso,
# MisProyectosPython/Semana_7/configurar_db.py): tablas usuarios y wallets,
# llave primaria, llave foranea id_propietario, saldo REAL y datos de prueba.
# Todo eso se conserva. Para enriquecer el ejercicio se adicionaron los
# elementos marcados con  [AGREGADO]:
#
#   Clase (Semana 6)                  Tabla
#   --------------------------------  ---------------------------------------
#   Usuario / UsuarioEmpresa          usuarios          (original, ampliada)
#   Wallet                            wallets           (original, ampliada)
#   Transaccion                       transacciones     [AGREGADO]
#   Empleado                          empleados         [AGREGADO]
#   UsuarioEmpresa <>-- Empleado      vinculaciones     [AGREGADO]
#   BancoCentral (Singleton)          configuracion_sistema [AGREGADO]
#
# Ejecutar:  python3 configurar_db.py

import sqlite3
from pathlib import Path

# La base se crea junto a este archivo, sin importar desde donde se ejecute.
RUTA_DB = Path(__file__).with_name("quantum_wallet.db")


# ======================================================================
# 1) ESQUEMA (DDL): tablas, llaves, restricciones, indices, vistas, triggers
# ======================================================================
ESQUEMA_SQL = """
-- ---------------------------------------------------------------------
-- [AGREGADO] configuracion_sistema  <-  clase BancoCentral (Singleton)
-- Una sola fila posible (id = 1): el Singleton llevado a la base de datos.
-- ---------------------------------------------------------------------
CREATE TABLE configuracion_sistema (
    id                  INTEGER PRIMARY KEY
                        CONSTRAINT ck_config_fila_unica CHECK (id = 1),
    moneda              TEXT    NOT NULL DEFAULT 'COP'
                        CONSTRAINT ck_config_moneda CHECK (length(moneda) = 3),
    limite_transaccion  REAL    NOT NULL
                        CONSTRAINT ck_config_limite CHECK (limite_transaccion > 0),
    fondos_totales      REAL    NOT NULL DEFAULT 0,
    reservas            REAL    NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------
-- usuarios  <-  clases Usuario, UsuarioEmpresa y Empleado
-- La jerarquia se guarda en una sola tabla con la columna tipo_usuario.
-- ---------------------------------------------------------------------
CREATE TABLE usuarios (
    id_usuario      INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_usuario    TEXT    NOT NULL DEFAULT 'PERSONA'             -- [AGREGADO]
                    CONSTRAINT ck_usuario_tipo
                    CHECK (tipo_usuario IN ('PERSONA', 'EMPRESA', 'EMPLEADO')),
    nombre          TEXT    NOT NULL
                    CONSTRAINT ck_usuario_nombre CHECK (length(trim(nombre)) > 0),
    email           TEXT    UNIQUE
                    CONSTRAINT ck_usuario_email
                    CHECK (email IS NULL OR email LIKE '%_@_%._%'),
    cedula          TEXT    UNIQUE,                                 -- [AGREGADO]
    nit             TEXT    UNIQUE,
    fecha_registro  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')), -- [AGREGADO]
    -- Solo las empresas tienen NIT, y toda empresa debe tenerlo
    CONSTRAINT ck_usuario_nit_empresa CHECK (
        (tipo_usuario = 'EMPRESA'  AND nit IS NOT NULL AND cedula IS NULL) OR
        (tipo_usuario <> 'EMPRESA' AND nit IS NULL)
    ),
    -- Todo empleado debe estar identificado con cedula
    CONSTRAINT ck_usuario_cedula_empleado CHECK (
        tipo_usuario <> 'EMPLEADO' OR cedula IS NOT NULL
    )
);

-- ---------------------------------------------------------------------
-- wallets  <-  clase Wallet
-- Composicion 1 a 1: cada usuario tiene exactamente una wallet
-- (UNIQUE en la FK) y la wallet desaparece con su dueno (ON DELETE CASCADE).
-- ---------------------------------------------------------------------
CREATE TABLE wallets (
    id_wallet       INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT    NOT NULL UNIQUE,                        -- [AGREGADO] id_billetera
    saldo           REAL    NOT NULL DEFAULT 0
                    CONSTRAINT ck_wallet_saldo_no_negativo CHECK (saldo >= 0),
    moneda          TEXT    NOT NULL DEFAULT 'COP'                  -- [AGREGADO]
                    CONSTRAINT ck_wallet_moneda CHECK (length(moneda) = 3),
    fecha_creacion  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')), -- [AGREGADO]
    id_propietario  INTEGER NOT NULL UNIQUE,
    FOREIGN KEY (id_propietario) REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- [AGREGADO] transacciones  <-  clase Transaccion
-- Composicion 1 a muchos: cada wallet guarda su historial de movimientos.
-- ---------------------------------------------------------------------
CREATE TABLE transacciones (
    id_transaccion        INTEGER PRIMARY KEY AUTOINCREMENT,
    id_wallet             INTEGER NOT NULL,
    tipo                  TEXT    NOT NULL
                          CONSTRAINT ck_transaccion_tipo CHECK (tipo IN
                          ('RECARGA', 'PAGO', 'TRANSFERENCIA_ENVIADA', 'TRANSFERENCIA_RECIBIDA')),
    monto                 REAL    NOT NULL
                          CONSTRAINT ck_transaccion_monto_positivo CHECK (monto > 0),
    saldo_resultante      REAL    NOT NULL
                          CONSTRAINT ck_transaccion_saldo CHECK (saldo_resultante >= 0),
    id_wallet_contraparte INTEGER,
    descripcion           TEXT,
    fecha                 TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (id_wallet) REFERENCES wallets(id_wallet) ON DELETE CASCADE,
    FOREIGN KEY (id_wallet_contraparte) REFERENCES wallets(id_wallet) ON DELETE SET NULL,
    CONSTRAINT ck_transaccion_contraparte CHECK (
        id_wallet_contraparte IS NULL OR id_wallet_contraparte <> id_wallet
    )
);

-- ---------------------------------------------------------------------
-- [AGREGADO] empleados  <-  clase Empleado (hereda de Usuario)
-- La PK es tambien FK: el empleado ES un usuario y solo agrega sus datos.
-- ---------------------------------------------------------------------
CREATE TABLE empleados (
    id_usuario  INTEGER PRIMARY KEY,
    cargo       TEXT    NOT NULL,
    salario     REAL    NOT NULL
                CONSTRAINT ck_empleado_salario CHECK (salario > 0),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- [AGREGADO] vinculaciones  <-  agregacion UsuarioEmpresa <>-- Empleado
-- Relacion muchos a muchos con llave primaria compuesta. Si se borra la
-- empresa se borra el vinculo, pero el empleado sigue existiendo.
-- ---------------------------------------------------------------------
CREATE TABLE vinculaciones (
    id_empresa         INTEGER NOT NULL,
    id_empleado        INTEGER NOT NULL,
    fecha_vinculacion  TEXT    NOT NULL DEFAULT (date('now', 'localtime')),
    PRIMARY KEY (id_empresa, id_empleado),
    FOREIGN KEY (id_empresa)  REFERENCES usuarios(id_usuario)   ON DELETE CASCADE,
    FOREIGN KEY (id_empleado) REFERENCES empleados(id_usuario)  ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- [AGREGADO] Indices para las consultas mas frecuentes
-- ---------------------------------------------------------------------
CREATE INDEX idx_transacciones_wallet_fecha ON transacciones (id_wallet, fecha);
CREATE INDEX idx_vinculaciones_empleado     ON vinculaciones (id_empleado);

-- ---------------------------------------------------------------------
-- [AGREGADO] Triggers: reglas del modelo de clases aplicadas en la base
-- ---------------------------------------------------------------------
-- Composicion: al registrar un usuario se crea su wallet, igual que
-- Usuario.__init__() crea self.__wallet = Wallet().
CREATE TRIGGER trg_usuario_crea_wallet
AFTER INSERT ON usuarios
BEGIN
    INSERT INTO wallets (codigo, moneda, id_propietario)
    VALUES ('W-' || printf('%05d', NEW.id_usuario),
            (SELECT moneda FROM configuracion_sistema WHERE id = 1),
            NEW.id_usuario);
END;

-- Equivalente a BancoCentral.validar_monto(): limite por transaccion.
CREATE TRIGGER trg_transaccion_valida_limite
BEFORE INSERT ON transacciones
WHEN NEW.monto > (SELECT limite_transaccion FROM configuracion_sistema WHERE id = 1)
BEGIN
    SELECT RAISE(ABORT, 'el monto supera el limite por transaccion');
END;

-- Solo un usuario de tipo EMPLEADO puede tener ficha de empleado.
CREATE TRIGGER trg_empleado_valida_tipo
BEFORE INSERT ON empleados
WHEN (SELECT tipo_usuario FROM usuarios WHERE id_usuario = NEW.id_usuario) <> 'EMPLEADO'
BEGIN
    SELECT RAISE(ABORT, 'el usuario no es de tipo EMPLEADO');
END;

-- Solo una EMPRESA puede vincular empleados.
CREATE TRIGGER trg_vinculacion_valida_empresa
BEFORE INSERT ON vinculaciones
WHEN (SELECT tipo_usuario FROM usuarios WHERE id_usuario = NEW.id_empresa) <> 'EMPRESA'
BEGIN
    SELECT RAISE(ABORT, 'solo una EMPRESA puede vincular empleados');
END;

-- ---------------------------------------------------------------------
-- [AGREGADO] Vistas: consultas listas para usar
-- ---------------------------------------------------------------------
CREATE VIEW vista_saldos AS
SELECT u.id_usuario, u.nombre, u.tipo_usuario, w.codigo, w.saldo, w.moneda
FROM usuarios u
JOIN wallets  w ON w.id_propietario = u.id_usuario;

CREATE VIEW vista_nomina AS
SELECT e.nombre AS empresa, u.nombre AS empleado, em.cargo, em.salario
FROM vinculaciones v
JOIN usuarios  e  ON e.id_usuario  = v.id_empresa
JOIN empleados em ON em.id_usuario = v.id_empleado
JOIN usuarios  u  ON u.id_usuario  = em.id_usuario;

CREATE VIEW vista_movimientos AS
SELECT t.id_transaccion, u.nombre AS titular, t.tipo, t.monto,
       t.saldo_resultante, t.descripcion, t.fecha
FROM transacciones t
JOIN wallets  w ON w.id_wallet  = t.id_wallet
JOIN usuarios u ON u.id_usuario = w.id_propietario;
"""


# ======================================================================
# 2) CONEXION
# ======================================================================
def conectar():
    """Abre la base y activa las llaves foraneas (SQLite las trae apagadas)."""
    conexion = sqlite3.connect(RUTA_DB)
    conexion.execute("PRAGMA foreign_keys = ON;")
    return conexion


def crear_esquema():
    """Crea la base desde cero para que el script se pueda repetir."""
    if RUTA_DB.exists():
        RUTA_DB.unlink()
    conexion = conectar()
    conexion.executescript(ESQUEMA_SQL)
    # Configuracion global del BancoCentral (Semana 6, Actividad 2)
    conexion.execute(
        "INSERT INTO configuracion_sistema (id, moneda, limite_transaccion, fondos_totales) "
        "VALUES (1, ?, ?, ?);",
        ("COP", 50_000_000, 1_000_000),
    )
    conexion.commit()
    return conexion


# ======================================================================
# 3) OPERACIONES DEL DOMINIO (parametros seguros con ?)
#    Cada operacion es atomica: "with conexion" confirma todo o revierte todo.
# ======================================================================
def registrar_usuario(conexion, nombre, email=None, cedula=None, nit=None, tipo="PERSONA"):
    """Inserta un usuario; el trigger le crea su wallet automaticamente."""
    with conexion:
        cursor = conexion.execute(
            "INSERT INTO usuarios (tipo_usuario, nombre, email, cedula, nit) "
            "VALUES (?, ?, ?, ?, ?);",
            (tipo, nombre, email, cedula, nit),
        )
    return cursor.lastrowid


def registrar_empleado(conexion, nombre, cedula, cargo, salario, email=None):    # [AGREGADO]
    """Empleado hereda de Usuario: fila en usuarios + fila en empleados."""
    with conexion:
        cursor = conexion.execute(
            "INSERT INTO usuarios (tipo_usuario, nombre, email, cedula) "
            "VALUES ('EMPLEADO', ?, ?, ?);",
            (nombre, email, cedula),
        )
        id_usuario = cursor.lastrowid
        conexion.execute(
            "INSERT INTO empleados (id_usuario, cargo, salario) VALUES (?, ?, ?);",
            (id_usuario, cargo, salario),
        )
    return id_usuario


def vincular_empleado(conexion, id_empresa, id_empleado):                       # [AGREGADO]
    with conexion:
        conexion.execute(
            "INSERT INTO vinculaciones (id_empresa, id_empleado) VALUES (?, ?);",
            (id_empresa, id_empleado),
        )


def _id_wallet(conexion, id_usuario):
    fila = conexion.execute(
        "SELECT id_wallet FROM wallets WHERE id_propietario = ?;", (id_usuario,)
    ).fetchone()
    if fila is None:
        raise ValueError(f"el usuario {id_usuario} no tiene wallet")
    return fila[0]


def _mover_saldo(conexion, id_wallet, monto, tipo, descripcion, contraparte=None, fecha=None):
    """Actualiza el saldo y deja el movimiento en el historial (sin commit).

    El monto llega siempre positivo; el tipo define si suma o resta. Si el
    monto es negativo o cero, el CHECK de la tabla transacciones lo rechaza y
    se revierte tambien la actualizacion del saldo.
    """
    delta = monto if tipo in ("RECARGA", "TRANSFERENCIA_RECIBIDA") else -monto
    conexion.execute(
        "UPDATE wallets SET saldo = round(saldo + ?, 2) WHERE id_wallet = ?;",
        (delta, id_wallet),
    )
    saldo = conexion.execute(
        "SELECT saldo FROM wallets WHERE id_wallet = ?;", (id_wallet,)
    ).fetchone()[0]
    conexion.execute(
        "INSERT INTO transacciones "
        "(id_wallet, tipo, monto, saldo_resultante, id_wallet_contraparte, descripcion, fecha) "
        "VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now', 'localtime')));",
        (id_wallet, tipo, monto, saldo, contraparte, descripcion, fecha),
    )
    return saldo


def recargar(conexion, id_usuario, monto, descripcion="Recarga", fecha=None):
    with conexion:
        return _mover_saldo(conexion, _id_wallet(conexion, id_usuario),
                            monto, "RECARGA", descripcion, fecha=fecha)


def realizar_pago(conexion, id_usuario, monto, descripcion="Pago", fecha=None):
    """Si el saldo no alcanza, el CHECK saldo >= 0 rechaza y se revierte todo."""
    with conexion:
        return _mover_saldo(conexion, _id_wallet(conexion, id_usuario),
                            monto, "PAGO", descripcion, fecha=fecha)


def transferir(conexion, id_origen, id_destino, monto, descripcion="Transferencia",
               fecha=None):                                                     # [AGREGADO]
    """Debito y credito en una sola transaccion: o pasan los dos o ninguno."""
    with conexion:
        w_origen = _id_wallet(conexion, id_origen)
        w_destino = _id_wallet(conexion, id_destino)
        _mover_saldo(conexion, w_origen, monto, "TRANSFERENCIA_ENVIADA",
                     descripcion, w_destino, fecha)
        _mover_saldo(conexion, w_destino, monto, "TRANSFERENCIA_RECIBIDA",
                     descripcion, w_origen, fecha)


def pagar_nomina(conexion, id_empresa):                                          # [AGREGADO]
    """UsuarioEmpresa.pagar_nomina(): transfiere el salario a cada empleado."""
    empleados = conexion.execute(
        "SELECT em.id_usuario, em.salario FROM vinculaciones v "
        "JOIN empleados em ON em.id_usuario = v.id_empleado "
        "WHERE v.id_empresa = ?;",
        (id_empresa,),
    ).fetchall()
    with conexion:
        w_empresa = _id_wallet(conexion, id_empresa)
        for id_empleado, salario in empleados:
            w_empleado = _id_wallet(conexion, id_empleado)
            _mover_saldo(conexion, w_empresa, salario, "TRANSFERENCIA_ENVIADA",
                         "Pago de nomina", w_empleado)
            _mover_saldo(conexion, w_empleado, salario, "TRANSFERENCIA_RECIBIDA",
                         "Pago de nomina", w_empresa)
    return sum(salario for _, salario in empleados)


# ======================================================================
# 4) DATOS DE PRUEBA (mismos escenarios de usuarios.py, Semana 6)
# ======================================================================
def insertar_datos_prueba(conexion):
    # --- Codigo original de la actividad ---
    ana = registrar_usuario(conexion, "Ana Torres", email="ana@quantum.com")
    bancolombia = registrar_usuario(conexion, "Bancolombia", email="contacto@bancolombia.com",
                                    nit="900123456-7", tipo="EMPRESA")
    recargar(conexion, ana, 100000)
    realizar_pago(conexion, ana, 30000, "Pago en comercio")
    recargar(conexion, bancolombia, 500000)
    realizar_pago(conexion, bancolombia, 200000, "Pago a proveedor")

    # --- [AGREGADO] Escenario de la version ampliada ---
    quantum = registrar_usuario(conexion, "Quantum SAS", email="pagos@quantum.com",
                                nit="901555222-1", tipo="EMPRESA")
    laura = registrar_empleado(conexion, "Laura Gomez", "1036123456", "Desarrolladora", 4500000,
                               email="laura.gomez@quantum.com")
    pedro = registrar_empleado(conexion, "Pedro Rios", "1017987654", "Analista", 3200000)
    recargar(conexion, quantum, 10000000, "Capital de trabajo")
    vincular_empleado(conexion, quantum, laura)
    vincular_empleado(conexion, quantum, pedro)
    pagar_nomina(conexion, quantum)
    # Transferencia con centavos: comprueba que REAL conserva los decimales
    transferir(conexion, laura, ana, 150000.50, "Devolucion de prestamo")


# ======================================================================
# 5) PRUEBAS DE INTEGRIDAD: operaciones invalidas que la base debe rechazar
# ======================================================================
def probar_integridad(conexion):
    pruebas = [
        ("Wallet con un propietario que no existe (FK)",
         lambda: conexion.execute(
             "INSERT INTO wallets (codigo, id_propietario) VALUES ('W-99999', 999);")),
        ("Segunda wallet para el mismo usuario (relacion 1 a 1)",
         lambda: conexion.execute(
             "INSERT INTO wallets (codigo, id_propietario) VALUES ('W-EXTRA', 1);")),
        ("Correo electronico repetido (UNIQUE)",
         lambda: registrar_usuario(conexion, "Ana Copia", email="ana@quantum.com")),
        ("Empresa registrada sin NIT (CHECK)",
         lambda: registrar_usuario(conexion, "Empresa sin NIT", tipo="EMPRESA")),
        ("Pago mayor al saldo disponible (CHECK saldo >= 0)",
         lambda: realizar_pago(conexion, 1, 99_000_000)),
        ("Recarga que supera el limite del Banco Central (trigger)",
         lambda: recargar(conexion, 1, 60_000_000)),
        ("Segunda fila de configuracion (Singleton)",
         lambda: conexion.execute(
             "INSERT INTO configuracion_sistema (id, limite_transaccion) VALUES (2, 1);")),
        ("Ficha de empleado para un usuario PERSONA (trigger)",
         lambda: conexion.execute(
             "INSERT INTO empleados (id_usuario, cargo, salario) VALUES (1, 'X', 1);")),
    ]
    print("\n[4] Pruebas de integridad (todas deben ser RECHAZADAS)")
    rechazadas = 0
    for descripcion, operacion in pruebas:
        try:
            operacion()
            conexion.commit()
            print(f"    ACEPTADA  {descripcion}")
        except sqlite3.DatabaseError as error:
            conexion.rollback()
            rechazadas += 1
            print(f"    RECHAZADA {descripcion}")
            print(f"              -> {type(error).__name__}: {error}")
    print(f"    Resultado: {rechazadas} de {len(pruebas)} operaciones invalidas rechazadas")


# ======================================================================
# 6) VERIFICACION
# ======================================================================
def verificar(conexion):
    print("\n[2] Estructura creada")
    objetos = conexion.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name;"
    ).fetchall()
    etiquetas = {"table": "Tablas", "index": "Indices", "trigger": "Triggers", "view": "Vistas"}
    for tipo, etiqueta in etiquetas.items():
        nombres = [n for t, n in objetos if t == tipo]
        print(f"    {etiqueta} ({len(nombres)}):")
        for nombre in nombres:
            print(f"      - {nombre}")

    print("\n[3] Datos de prueba")
    print("    Saldos por usuario (vista_saldos):")
    for id_u, nombre, tipo, codigo, saldo, moneda in conexion.execute(
            "SELECT * FROM vista_saldos ORDER BY id_usuario;"):
        print(f"      {id_u}  {nombre:<12} {tipo:<9} {codigo}  {saldo:>15,.2f} {moneda}")
    print("    Nomina (vista_nomina):")
    for empresa, empleado, cargo, salario in conexion.execute("SELECT * FROM vista_nomina;"):
        print(f"      {empresa} -> {empleado:<12} {cargo:<15} {salario:>13,.2f}")
    total = conexion.execute("SELECT count(*) FROM transacciones;").fetchone()[0]
    print(f"    Transacciones registradas: {total}")

    descuadres = conciliar(conexion)
    print("    Conciliacion saldo vs. historial:",
          "correcta en todas las wallets" if not descuadres else f"descuadre en {descuadres}")


def conciliar(conexion):                                                         # [AGREGADO]
    """Devuelve los codigos de las wallets cuyo saldo no coincide con su historial."""
    filas = conexion.execute("""
        SELECT w.codigo FROM wallets w
        LEFT JOIN transacciones t ON t.id_wallet = w.id_wallet
        GROUP BY w.id_wallet
        HAVING round(w.saldo - coalesce(sum(CASE WHEN t.tipo IN ('RECARGA','TRANSFERENCIA_RECIBIDA')
                                         THEN t.monto ELSE -t.monto END), 0), 2) <> 0;
    """).fetchall()
    return [codigo for (codigo,) in filas]


def probar_autoincrement_y_cascada(conexion):
    print("\n[5] AUTOINCREMENT y borrado en cascada")
    temporal = registrar_usuario(conexion, "Usuario Temporal")
    recargar(conexion, temporal, 1000)
    with conexion:
        conexion.execute("DELETE FROM usuarios WHERE id_usuario = ?;", (temporal,))
    huerfanas = conexion.execute(
        "SELECT count(*) FROM wallets WHERE id_propietario = ?;", (temporal,)
    ).fetchone()[0]
    nuevo = registrar_usuario(conexion, "Usuario Nuevo")
    print(f"    Se creo y se borro el usuario {temporal}; wallets huerfanas: {huerfanas}")
    print(f"    El siguiente usuario recibio el id {nuevo} (el {temporal} no se reutiliza)")
    with conexion:  # se retira para dejar limpios los datos de prueba
        conexion.execute("DELETE FROM usuarios WHERE id_usuario = ?;", (nuevo,))


# ======================================================================
# PROGRAMA PRINCIPAL
# ======================================================================
if __name__ == "__main__":
    print("=" * 74)
    print(" QUANTUM CORE - Configuracion de la base de datos quantum_wallet.db")
    print("=" * 74)
    print(f"[1] SQLite {sqlite3.sqlite_version} - archivo: {RUTA_DB.name}")
    print("    PRAGMA foreign_keys = ON")

    conexion = crear_esquema()
    insertar_datos_prueba(conexion)
    verificar(conexion)
    probar_integridad(conexion)
    probar_autoincrement_y_cascada(conexion)

    conexion.close()   # cerrar la conexion (buena practica)
    print("\nBase de datos creada y verificada:", RUTA_DB.name)
