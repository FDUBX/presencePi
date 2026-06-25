# Guide pas-à-pas — presencePi (from scratch → production)

Suivre les phases **dans l'ordre**. Chaque étape a un critère de vérification ✅.
Ne pas passer à la suivante tant que le ✅ n'est pas obtenu.

Légende : 💻 = sur ton PC · 🍓 = sur le Pi (SSH) · 🔌 = manip matérielle (Pi **éteint**)

---

## Phase 0 — Réception & vérification des pièces

- [ ] Pi Zero 2W, capteur LD2450, module IR Haljia, câbles Dupont F-F 3 broches + 120 pcs,
      micro SD 16 Go, boîtier, chargeur micro USB.
- [ ] Inspection visuelle : pas de broche tordue sur le LD2450 ni le Haljia.
- [ ] Identifier le **connecteur JST 4 broches** du LD2450 (TX/RX/VCC/GND) et le pinout
      Haljia **(1) DAT — (2) VCC — (3) GND**.

✅ Toutes les pièces présentes et identifiées. **Ne rien câbler encore.**

---

## Phase 1 — Préparer la carte SD (OS headless) 💻

1. Installer **Raspberry Pi Imager**.
2. Choix : **Raspberry Pi OS Lite (64-bit)** (sans desktop).
3. Roue crantée ⚙️ AVANT de flasher :
   - Hostname : `presence-tv`
   - Activer **SSH** (auth par mot de passe ou clé)
   - Utilisateur : `pi` + mot de passe
   - Wi-Fi : SSID + mot de passe + pays `FR` (ou `CH`)
   - Locale/clavier au besoin
4. Flasher, puis insérer la SD dans le Pi.

✅ Carte flashée avec SSH + Wi-Fi pré-configurés.

> ⚠️ Ne **pas** brancher le LD2450 ni le Haljia pour ce premier boot.

---

## Phase 2 — Premier boot & accès SSH 💻🍓

1. Brancher l'alimentation (port USB **PWR**, pas le port DATA). Attendre ~60 s.
2. SSH :
   ```bash
   ssh pi@presence-tv.local
   ```
   Si mDNS KO, trouver l'IP :
   ```bash
   nmap -sn 192.168.1.0/24 | grep -B2 -i raspberry   # ou box/routeur
   ```
3. Mises à jour :
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   ```

✅ Connecté en SSH, système à jour.

---

## Phase 3 — Configuration système (UART + IR) 🍓

### 3.1 Overlays /boot
Éditer `/boot/firmware/config.txt` (Bookworm ; sinon `/boot/config.txt`) et ajouter en fin
(contenu de `config/config.txt.snippet`) :
```ini
dtoverlay=disable-bt
dtoverlay=gpio-ir-tx,gpio_pin=17
```
Puis libérer l'UART du Bluetooth :
```bash
sudo systemctl disable hciuart
```

### 3.2 Désactiver la console série
```bash
sudo raspi-config
# Interface Options → Serial Port
#   Login shell over serial : NO
#   Serial port hardware    : YES
```

### 3.3 Redémarrer
```bash
sudo reboot
```

### 3.4 Vérifications après reboot
```bash
ls -l /dev/ttyAMA0      # doit exister (PL011 sur GPIO14/15)
ls -l /dev/lirc0        # doit exister (émetteur IR)
ir-ctl -d /dev/lirc0 --features    # liste les capacités TX
```

✅ `/dev/ttyAMA0` ET `/dev/lirc0` présents. `hciuart` désactivé.

---

## Phase 4 — Déploiement du code 🍓

1. Récupérer le repo sur le Pi (git clone, ou `scp -r` depuis le PC).
2. Depuis la racine du repo :
   ```bash
   sudo ./install.sh
   ```
   Installe deps (`python3-serial`, `v4l-utils`...), crée l'utilisateur `presence`,
   copie vers `/opt/presence_tv`, installe le service (sans le démarrer).

✅ `/opt/presence_tv/presence_tv.py` présent, service `presence-tv` *enabled* mais pas encore *started*.

---

## Phase 5 — Câblage matériel 🔌

> **Pi ÉTEINT et débranché.** Manipuler par les bords.

### 5.1 LD2450 → Pi
```
LD2450 TX  → pin 10 (GPIO15 RXD)
LD2450 RX  → pin 8  (GPIO14 TXD)
LD2450 VCC → pin 2  (5V)
LD2450 GND → pin 6  (GND)
```
### 5.2 Module IR Haljia → Pi
```
Haljia VCC (2) → pin 4  (5V)
Haljia GND (3) → pin 14 (GND)
Haljia DAT (1) → pin 11 (GPIO17)
```

Double-vérifier **VCC/GND** (inversion = court-circuit). Rebrancher l'alim, booter.

✅ Câblage conforme, Pi rebooté sans odeur/chaleur anormale, SSH de nouveau accessible.

---

## Phase 6 — Test capteur LD2450 🍓

Moniteur live (n'utilise pas le service). Depuis la racine du repo cloné :
```bash
python3 tools/ld2450_monitor.py --port /dev/ttyAMA0 --baud 256000
```
- Se déplacer devant le capteur → des lignes `T0: x=... y=... res=...` apparaissent.
- S'éloigner / sortir du champ → `(aucune cible)`.
- Vérifier la cohérence des signes : se décaler à droite → `x` augmente ; reculer → `y` augmente.

✅ Cibles détectées, coordonnées qui bougent de façon cohérente (signe correct = fix décodage OK).

> Si rien ne s'affiche : UART pas libéré (Phase 3), mauvais TX/RX (croisé ?), ou baud.
> Tester `sudo cat /dev/ttyAMA0 | xxd | head` → doit montrer des `aa ff 03 00`.

---

## Phase 7 — Test IR (codes Samsung) 🍓

### 7.1 Générer les trames
```bash
cd /opt/presence_tv
python3 samsung_ir_gen.py 0xE0E09768 | sudo tee ir/hdmi1.txt   # HDMI1
python3 samsung_ir_gen.py 0xE0E0D728 | sudo tee ir/hdmi2.txt   # HDMI2 (à confirmer)
```

### 7.2 Vérifier l'émission (caméra smartphone)
```bash
ir-ctl -d /dev/lirc0 --send=ir/hdmi1.txt
```
Pointer le module vers la caméra → la LED doit clignoter **violet/blanc**.

### 7.3 Test sur la TV
- Mettre la TV sur HDMI2 manuellement, pointer le module vers le récepteur IR de la TV (1-2 m, ligne directe).
- `ir-ctl -d /dev/lirc0 --send=ir/hdmi1.txt` → la TV doit basculer sur HDMI1. Idem hdmi2.txt.

**Si la TV ne réagit pas :**
1. Régénérer en LSB-first : `python3 samsung_ir_gen.py --lsb 0xE0E09768 | sudo tee ir/hdmi1.txt`.
2. Si toujours KO ou « Not Available » : capturer depuis la télécommande **BN59-01259B**.
   Ajouter `dtoverlay=gpio-ir,gpio_pin=18` à config.txt, reboot, brancher un récepteur IR
   (TSOP1738/KY-022) sur GPIO18, puis :
   ```bash
   ir-ctl -d /dev/lirc1 --receive=ir/hdmi1.txt   # appuyer Source→HDMI1, Ctrl+C
   ```

✅ Les deux fichiers IR font effectivement basculer la TV.

---

## Phase 8 — Réglages (zone & timeout) 🍓

Avec `tools/ld2450_monitor.py`, relever les `x`/`y` aux limites de la zone utile
(canapé / position d'usage). Éditer `/opt/presence_tv/presence_tv.ini` :
```ini
[presence]
timeout_s = 30          # délai d'absence avant HDMI2

[zone]
enabled = true          # activer le filtrage
x_min = -1500
x_max =  1500
y_min =  300
y_max =  3500

[ir]
repeat = 2              # 1 si un seul envoi suffit
```

✅ Zone calée sur la pièce, timeout choisi.

---

## Phase 9 — Test d'intégration (service) 🍓

```bash
sudo systemctl start presence-tv
journalctl -fu presence-tv
```
Scénarios à valider (observer les logs `Switch TV -> HDMI x`) :
1. Entrer dans la zone → bascule **HDMI1** (quasi immédiat).
2. Quitter la zone, attendre `timeout_s` → bascule **HDMI2**.
3. Re-rentrer avant la fin du timeout → reste/repasse **HDMI1**, pas de bascule parasite.
4. Pas de spam IR quand l'entrée est déjà la bonne.

✅ Les 4 scénarios passent, TV pilotée correctement.

---

## Phase 10 — Mise en production 🍓

### 10.1 Persistance au boot
Déjà *enabled* (Phase 4). Vérifier :
```bash
systemctl is-enabled presence-tv     # → enabled
sudo reboot
# après reboot :
systemctl status presence-tv         # → active (running)
```

### 10.2 (Optionnel) IP fixe
```bash
sudo nmcli con mod "<SSID>" \
  ipv4.addresses 192.168.1.50/24 \
  ipv4.gateway 192.168.1.1 \
  ipv4.dns 192.168.1.1 \
  ipv4.method manual
sudo nmcli con up "<SSID>"
```

### 10.3 Test de redémarrage à froid
Couper l'alim 10 s, rebrancher. Sans intervention :
```bash
journalctl -u presence-tv -b   # le service a démarré seul
```
Vérifier qu'une présence pilote bien la TV après ce cold boot.

### 10.4 Montage final
Fixer le boîtier, orienter le LD2450 vers la zone, le module IR en ligne directe vers la TV.

✅ Service actif, survit au reboot et au cold boot, TV pilotée. **Production OK.**

---

## Annexe — Dépannage rapide

| Symptôme | Piste |
|----------|-------|
| Pas de `/dev/ttyAMA0` | `disable-bt` absent de config.txt / pas reboot |
| Pas de `/dev/lirc0` | `gpio-ir-tx` absent / mauvais GPIO |
| Capteur muet | UART occupé par getty (raspi-config), TX/RX inversés, mauvais baud |
| Coords incohérentes | Devrait être OK (décodage signe+magnitude) — vérifier câblage GND |
| LED IR invisible caméra | VCC pas sur 5V, DAT mal câblé |
| TV ne réagit pas à l'IR | Mauvais code/ordre bits (`--lsb`), distance/angle, capturer la télécommande |
| Bascule HDMI2 parasite | `timeout_s` trop court, ou zone trop restrictive |
| Service ne démarre pas | `journalctl -u presence-tv` ; droits groupe `dialout`/`video` |
| Permission denied UART/lirc | utilisateur `presence` pas dans `dialout`/`video` (relancer install.sh) |
