#!/usr/bin/env bash
#
# Actualiza VIA Compras en el servidor con la última versión de main.
#
# Uso, en el servidor y como el usuario «via»:
#   /srv/via-compras/despliegue/actualizar.sh
#
# Qué hace, en orden:
#   1. Trae el código nuevo.
#   2. Instala las dependencias.
#   3. Verifica la configuración de Django.
#   4. Respalda la base de datos (si es PostgreSQL).
#   5. Aplica las migraciones y reúne los estáticos.
#   6. Reinicia el servicio y comprueba que quedó arriba.
#
# Si cualquier paso falla, el script se detiene y vuelve el código a la versión
# que estaba corriendo. Las migraciones en PostgreSQL son transaccionales: una
# que falla no deja la base a medias. El respaldo del paso 4 queda para el caso
# en que haya que deshacer una migración que sí se aplicó.

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/via-compras}"
RAMA="${RAMA:-main}"
PY="$APP_DIR/.venv/bin/python"

cd "$APP_DIR"
ANTERIOR="$(git rev-parse HEAD)"
REINICIADO=0

volver_atras() {
    echo
    echo "!! Falló la actualización. Vuelvo el código a ${ANTERIOR:0:7}."
    git reset -q --hard "$ANTERIOR"
    "$APP_DIR/.venv/bin/pip" install -q -r requirements.txt
    # Si el fallo fue después de reiniciar, el servicio ya cargó el código
    # nuevo: hay que levantarlo otra vez con el anterior.
    if [ "$REINICIADO" -eq 1 ]; then
        sudo systemctl restart via-compras || true
    fi
    echo "!! El servicio queda con la versión anterior. Revisa el error de arriba."
}
trap volver_atras ERR

echo "==> 1/6 Trayendo $RAMA"
git fetch -q origin "$RAMA"
git checkout -q "$RAMA"
git merge -q --ff-only "origin/$RAMA"

echo "==> 2/6 Instalando dependencias"
"$APP_DIR/.venv/bin/pip" install -q -r requirements.txt

echo "==> 3/6 Verificando la configuración"
"$PY" manage.py check
# Informativo: avisa, por ejemplo, si falta configurar el correo SMTP, pero no
# detiene la actualización.
"$PY" manage.py check --deploy || echo "   (revisa los avisos de arriba)"

echo "==> 4/6 Respaldando la base de datos"
# La etiqueta es la versión que estaba corriendo: si hay que deshacer, se sabe
# a qué código corresponde el respaldo.
"$APP_DIR/despliegue/respaldar.sh" "antes-de-${ANTERIOR:0:7}"

echo "==> 5/6 Migraciones y estáticos"
"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput --verbosity 0

echo "==> 6/6 Reiniciando el servicio"
REINICIADO=1
sudo systemctl restart via-compras
sleep 3
if ! systemctl is-active --quiet via-compras; then
    journalctl -u via-compras -n 40 --no-pager
    false  # dispara volver_atras
fi

trap - ERR
echo
echo "Listo: VIA Compras corre la versión $(git rev-parse --short HEAD)."
