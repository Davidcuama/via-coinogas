# Despliegue de VIA Compras en AWS EC2

Guía para montar el servidor desde cero y para actualizarlo después. La versión
narrada, con el despliegue real del proyecto, está en la Wiki.

## Arquitectura

```
Navegador ──HTTPS──▶ nginx ──socket──▶ gunicorn ──▶ Django ──▶ PostgreSQL
                       │                               │
                  certificado                     adjuntos en disco
                 (Let's Encrypt)                (/srv/via-compras/media)
```

- **EC2 y no App Runner:** los adjuntos de HU-11 se guardan en el disco del
  servidor. En EC2 ese disco persiste; en App Runner se borra en cada
  redespliegue.
- **nginx** recibe el tráfico, termina el HTTPS y pasa la petición a gunicorn.
  No sirve los adjuntos: esos pasan por una vista de Django que revisa permisos.
- **WhiteNoise** sirve el CSS, el logo y los scripts desde Django.
- **PostgreSQL** corre en la misma instancia.

## Archivos de esta carpeta

| Archivo | Qué es |
|---|---|
| `via-compras.service` | Servicio de systemd que mantiene gunicorn corriendo. |
| `nginx-via-compras.conf` | Sitio de nginx. |
| `actualizar.sh` | Actualiza el servidor a la última versión de `main`, con vuelta atrás si algo falla. |
| `respaldar.sh` | Respalda la base de datos. |
| `crontab` | Tareas programadas: respaldo diario y actualización del tablero (HU-33). |

## Instalación inicial

Supone Ubuntu Server 24.04 LTS. Los comandos con `sudo` se corren con el
usuario `ubuntu` que crea AWS; los demás, con el usuario `via`.

### 1. La instancia

En la consola de AWS (EC2 → Lanzar instancia):

- **AMI:** Ubuntu Server 24.04 LTS.
- **Tipo:** `t3.small` (2 GB). `t3.micro` (1 GB, capa gratuita) también sirve,
  agregando memoria de intercambio (paso 2).
- **Almacenamiento:** 20 GB.
- **Grupo de seguridad:** SSH (22) **solo desde tu IP**; HTTP (80) y HTTPS (443)
  desde cualquier lugar.
- **IP elástica** asociada a la instancia, para que la dirección no cambie al
  reiniciar: el dominio y el certificado dependen de ella.

### 2. Paquetes y zona horaria

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-dev postgresql nginx certbot python3-certbot-nginx git
sudo timedatectl set-timezone America/Bogota
```

Solo en `t3.micro`, memoria de intercambio de 1 GB:

```bash
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3. Usuario y código

El usuario `via` corre la aplicación; su casa queda en `/home/via` y el
código en `/srv/via-compras`, que es de él y del grupo de nginx.

```bash
sudo adduser --system --group --home /home/via --shell /bin/bash via
sudo usermod -aG www-data via
sudo mkdir -p /srv/via-compras
sudo chown via:www-data /srv/via-compras
sudo -iu via
git clone https://github.com/Davidcuama/via-coinogas.git /srv/via-compras
cd /srv/via-compras
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p media registros respaldos
exit
```

### 4. Base de datos

```bash
sudo -u postgres psql
```

```sql
CREATE ROLE via_app WITH LOGIN PASSWORD 'UNA-CLAVE-LARGA';
CREATE DATABASE via_coinogas OWNER via_app;
\q
```

### 5. Configuración

```bash
sudo -iu via
cd /srv/via-compras
cp .env.example .env
chmod 600 .env
nano .env
```

Valores de producción (el resto como en `.env.example`):

```
SECRET_KEY=<generar con el comando que indica .env.example>
DEBUG=False
ALLOWED_HOSTS=<DOMINIO>
USAR_HTTPS=False          # se activa en el paso 9, con el certificado puesto
CSRF_TRUSTED_ORIGINS=https://<DOMINIO>
DB_ENGINE=postgresql
DB_NAME=via_coinogas
DB_USER=via_app
DB_PASSWORD=UNA-CLAVE-LARGA
DB_HOST=localhost
DB_PORT=5432
EMAIL_HOST=<servidor SMTP de Coinogas>
EMAIL_HOST_USER=<cuenta>
EMAIL_HOST_PASSWORD=<clave>
COMPRAS_EMAILS=<buzones del área de compras>
```

**Dominio:** si no hay uno propio, sirve `<IP-con-guiones>.sslip.io` (por
ejemplo `3-90-12-45.sslip.io` para la IP 3.90.12.45). Resuelve solo a esa IP y
Let's Encrypt le emite certificado.

### 6. Datos iniciales

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py cargar_catalogos
.venv/bin/python manage.py crear_perfiles
.venv/bin/python manage.py crear_usuarios_cliente     # imprime las claves una sola vez
.venv/bin/python manage.py createsuperuser
exit
```

Las áreas y los centros de costo reales se cargan desde `/admin`.

Opcional, para el tablero de Power BI: el rol de solo lectura de HU-29.

```bash
sudo -iu via bash -c 'cd /srv/via-compras && .venv/bin/python manage.py crear_rol_analitica --password "<otra-clave>"'
```

### 7. Servicio

```bash
sudo cp /srv/via-compras/despliegue/via-compras.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now via-compras
systemctl status via-compras
```

`actualizar.sh` reinicia el servicio con `sudo`; se le da ese único permiso:

```bash
echo 'via ALL=(root) NOPASSWD: /usr/bin/systemctl restart via-compras' | sudo tee /etc/sudoers.d/via-compras
sudo chmod 440 /etc/sudoers.d/via-compras
```

### 8. nginx

```bash
sudo cp /srv/via-compras/despliegue/nginx-via-compras.conf /etc/nginx/sites-available/via-compras
sudo sed -i 's/DOMINIO/<DOMINIO>/' /etc/nginx/sites-available/via-compras
sudo ln -s /etc/nginx/sites-available/via-compras /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

En este punto el sitio ya responde por HTTP en `http://<DOMINIO>`.

### 9. HTTPS

```bash
sudo certbot --nginx -d <DOMINIO> --redirect -m <correo> --agree-tos -n
```

Certbot agrega el bloque HTTPS, la redirección desde HTTP y la renovación
automática. Con el certificado puesto, en `.env`:

```
USAR_HTTPS=True
```

```bash
sudo systemctl restart via-compras
```

### 10. Tareas programadas

```bash
sudo -iu via crontab /srv/via-compras/despliegue/crontab
```

Quedan dos tareas: el respaldo de la base a las 2:30 a. m. y la actualización
de los datos del tablero de Power BI a las 6:00 a. m. (HU-33). Para no esperar
a la primera corrida del tablero:

```bash
sudo -iu via bash -c 'cd /srv/via-compras && .venv/bin/python manage.py actualizar_tablero'
```

## Actualizar a una versión nueva

Cuando se mergea algo a `main`:

```bash
sudo -iu via /srv/via-compras/despliegue/actualizar.sh
```

Trae el código, instala dependencias, verifica, respalda la base, migra, reúne
estáticos y reinicia. Si un paso falla, vuelve el código a la versión que
estaba corriendo y se detiene.

## Operación

| Para… | Comando |
|---|---|
| Ver si está arriba | `systemctl status via-compras` |
| Ver los registros en vivo | `journalctl -u via-compras -f` |
| Errores de nginx | `sudo tail -f /var/log/nginx/error.log` |
| Respaldar ya | `sudo -iu via /srv/via-compras/despliegue/respaldar.sh manual` |
| Actualizar el tablero ya | `sudo -iu via bash -c 'cd /srv/via-compras && .venv/bin/python manage.py actualizar_tablero'` |
| Ver las corridas del tablero | `tail /srv/via-compras/registros/tablero.log` |
| Restaurar un respaldo | `PGPASSWORD='<DB_PASSWORD>' pg_restore -h localhost -U via_app --clean -d via_coinogas <archivo>` |
| Renovar el certificado (automático) | `sudo certbot renew --dry-run` para probar |
