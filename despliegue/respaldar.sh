#!/usr/bin/env bash
#
# Respalda la base de datos PostgreSQL de VIA Compras.
#
# Lo usa actualizar.sh antes de cada migración, y lo corre una tarea diaria
# (ver despliegue/crontab). Atiende el riesgo R9 del caso de negocio: sin
# respaldos, una falla del disco o una migración mala se lleva todos los
# requerimientos.
#
# Uso, en el servidor y como el usuario «via»:
#   /srv/via-compras/despliegue/respaldar.sh [etiqueta]
#
# Deja un archivo en formato propio de PostgreSQL, que se restaura con:
#   PGPASSWORD='<DB_PASSWORD>' pg_restore -h localhost -U via_app --clean \
#       -d via_coinogas <archivo>

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/via-compras}"
RESPALDOS="${RESPALDOS:-$APP_DIR/respaldos}"
# Una semana de respaldos diarios, más los de las actualizaciones recientes.
CONSERVAR="${CONSERVAR:-10}"
ETIQUETA="${1:-diario}"

cd "$APP_DIR"

# Lee una variable del .env sin ejecutarlo: el archivo tiene valores con
# espacios y signos (<, >) que romperían un `source`.
leer_env() {
    grep -E "^$1=" .env | tail -n 1 | cut -d= -f2-
}

if [ "$(leer_env DB_ENGINE)" = "sqlite" ]; then
    echo "Base SQLite: no se respalda con este script."
    exit 0
fi

mkdir -p "$RESPALDOS"
chmod 700 "$RESPALDOS"
ARCHIVO="$RESPALDOS/via-$(date +%Y%m%d-%H%M%S)-$ETIQUETA.dump"

PGPASSWORD="$(leer_env DB_PASSWORD)" pg_dump \
    --format=custom \
    --host="$(leer_env DB_HOST)" \
    --port="$(leer_env DB_PORT)" \
    --username="$(leer_env DB_USER)" \
    --file="$ARCHIVO" \
    "$(leer_env DB_NAME)"

echo "Respaldo: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"

# Solo se conservan los más recientes, para no llenar el disco.
ls -1t "$RESPALDOS"/via-*.dump | tail -n +$((CONSERVAR + 1)) | xargs -r rm --
