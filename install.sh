#!/usr/bin/env bash
# Déploiement du détecteur de présence sur Raspberry Pi.
# À exécuter SUR le Pi, depuis la racine du repo : sudo ./install.sh
set -euo pipefail

DEST=/opt/presence_tv
SERVICE=presence-tv.service
USER_SVC=presence

if [[ $EUID -ne 0 ]]; then
  echo "Lancer avec sudo." >&2
  exit 1
fi

echo "==> Dépendances"
apt-get update
apt-get install -y python3-pip python3-serial ir-keytable v4l-utils

echo "==> Utilisateur de service ($USER_SVC)"
if ! id "$USER_SVC" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$USER_SVC"
fi
usermod -aG dialout,video "$USER_SVC"

echo "==> Copie des fichiers vers $DEST"
mkdir -p "$DEST/ir"
install -m 644 src/presence_tv.py        "$DEST/presence_tv.py"
install -m 644 src/samsung_ir_gen.py     "$DEST/samsung_ir_gen.py"
install -m 644 ir/hdmi1.txt              "$DEST/ir/hdmi1.txt"
install -m 644 ir/hdmi2.txt              "$DEST/ir/hdmi2.txt"

# Ne pas écraser une config existante
if [[ ! -f "$DEST/presence_tv.ini" ]]; then
  install -m 644 config/presence_tv.ini "$DEST/presence_tv.ini"
else
  echo "    config existante conservée : $DEST/presence_tv.ini"
fi

echo "==> Accès UART (ttyAMA0 en group dialout)"
# ttyAMA0 naît parfois root:tty 600 (réclamé comme console) -> l'utilisateur
# 'presence' (group dialout) ne peut pas l'ouvrir. Règle udev = group dialout
# persistant au reboot ; mask getty = aucune console ne squatte le port.
cat > /etc/udev/rules.d/99-ttyama0.rules <<'RULE'
KERNEL=="ttyAMA0", GROUP="dialout", MODE="0660"
RULE
systemctl mask serial-getty@ttyAMA0.service
udevadm control --reload-rules
udevadm trigger --action=add --subsystem-match=tty --sysname-match=ttyAMA0 || true

echo "==> Service systemd"
install -m 644 "systemd/$SERVICE" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl enable "$SERVICE"

cat <<EOF

Installation terminée.

ÉTAPES MANUELLES RESTANTES :
  1. Ajouter le contenu de config/config.txt.snippet à /boot/firmware/config.txt
     puis : sudo systemctl disable hciuart && sudo reboot
  2. Générer les fichiers IR réels :
       python3 $DEST/samsung_ir_gen.py 0xE0E09768 | sudo tee $DEST/ir/hdmi1.txt
       python3 $DEST/samsung_ir_gen.py 0xE0E0D728 | sudo tee $DEST/ir/hdmi2.txt
     (valider avec caméra smartphone : ir-ctl -d /dev/lirc0 --send=$DEST/ir/hdmi1.txt)
  3. Login série déjà neutralisé (serial-getty masqué + règle udev dialout).
     Vérifier que le hardware UART est activé : raspi-config -> Interface -> Serial Port
       Login shell : No / Serial hardware : Yes  (sinon /dev/ttyAMA0 absent)
  4. Démarrer : sudo systemctl start $SERVICE
     Logs     : journalctl -fu $SERVICE
     Vérifier : ls -l /dev/ttyAMA0  -> crw-rw---- root dialout
EOF
