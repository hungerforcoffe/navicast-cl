# Grabador AIS 24/7 en AWS EC2 (free tier)

Corre `scripts/record_aisstream.py` en una instancia EC2 siempre encendida, subiendo
los Parquet a tu bucket S3. Tu laptop solo lee de S3 cuando proceses. Free tier:
`t3.micro` 750 h/mes durante 12 meses = 24/7 gratis.

## 1. Rol IAM (S3 sin llaves en el servidor)
Consola **IAM -> Roles -> Create role -> AWS service -> EC2**. Adjunta esta politica
inline (minimo privilegio: solo escribir en el prefijo del grabador):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "s3:PutObject",
    "Resource": "arn:aws:s3:::navicast-cl-pr2026/bronze/source=aisstream/*"
  }]
}
```
Nombre del rol: `navicast-ec2-recorder`.

## 2. Lanzar la instancia
**EC2 -> Launch instance**:
- AMI: **Ubuntu Server 24.04 LTS** (trae Python 3.12).
- Tipo: **t3.micro** (free-tier eligible).
- Key pair: crea/usa una para SSH.
- Security group: permitir **SSH (22) solo desde tu IP**. (El grabador solo hace
  conexiones salientes; no necesita puertos de entrada.)
- **Advanced details -> IAM instance profile:** elige `navicast-ec2-recorder`.
- Disco 8 GB por defecto basta (los Parquet van a S3, no se acumulan localmente mucho).

## 3. Configurar la instancia (por SSH)
```bash
ssh -i tu_clave.pem ubuntu@<IP_PUBLICA>

sudo apt update && sudo apt install -y python3-venv git
# Trae el repo: empuja NaviCast-CL a un repo GitHub (privado) y clonalo aqui,
# o copialo con scp. Ejemplo si esta en GitHub:
git clone https://github.com/<tu_usuario>/NaviCast-CL.git
cd NaviCast-CL

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[chile]"        # boto3, pyyaml, pyarrow, websockets, pandas
```

## 4. Token de aisstream (fuera del repo)
```bash
echo 'AISSTREAM_API_KEY=TU_API_KEY' | sudo tee /etc/navicast.env
sudo chmod 600 /etc/navicast.env
```

## 5. Servicio systemd (se reinicia solo)
```bash
sudo cp deploy/navicast-recorder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now navicast-recorder
systemctl status navicast-recorder          # debe decir "active (running)"
journalctl -u navicast-recorder -f          # ver los logs en vivo
```
`Restart=always` lo revive si crashea; `enable` lo arranca al reiniciar la maquina.

## 6. Verificar que llega a S3
Desde tu laptop:
```powershell
.venv\Scripts\python -c "from navicast.common import config, io_s3; c=config.load(); cl=io_s3.get_client(c['aws']['region']); print([o['Key'] for o in cl.list_objects_v2(Bucket=c['aws']['bucket'], Prefix='bronze/source=aisstream/').get('Contents',[])][:10])"
```

## Cuando tengas datos
`clean.run("snap_chile_valpo_v1")` se reutiliza. Falta parametrizar el poligono de
puerto para Chile (Valparaiso/San Antonio) antes de `features`/`viz` (ver
docs/sprints.md y la memoria del proyecto).

## Costos / apagar
Free tier cubre 1 instancia `t3.micro` 24/7 por 12 meses. Cuando termines de grabar,
**detén o termina la instancia** desde la consola para no gastar (la data ya esta en S3).
