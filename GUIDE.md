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

> ⚠️ Sur certaines images, `/dev/ttyAMA0` naît quand même `root:tty 600` (réclamé
> comme console) → l'utilisateur `presence` ne peut pas l'ouvrir (`Permission denied`).
> `install.sh` corrige ça (règle udev `99-ttyama0.rules` + `mask serial-getty@ttyAMA0`).
> Si tu n'as pas (re)lancé install.sh, applique à la main :
> ```bash
> echo 'KERNEL=="ttyAMA0", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/99-ttyama0.rules
> sudo systemctl mask serial-getty@ttyAMA0.service
> sudo udevadm control --reload-rules
> sudo udevadm trigger --action=add --subsystem-match=tty --sysname-match=ttyAMA0
> ls -l /dev/ttyAMA0   # doit être crw-rw---- root dialout
> ```

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

### 7.4 Test "clé en main" sur place — `tools/ir_onsite.sh`

Quand la validation IR ne peut se faire **que devant la TV**, ce script enchaîne tout :
```bash
sudo ./tools/ir_onsite.sh          # diagnostic + boucle caméra + essai des codes
sudo ./tools/ir_onsite.sh --loop-only   # juste la boucle caméra (test émission)
sudo ./tools/ir_onsite.sh --try-only    # juste l'essai séquentiel sur la TV
```
- **Phase 1** : vérifie que `lirc0` supporte SEND + overlay chargé.
- **Phase 2** : envoie HDMI1 en boucle 20 s → tu filmes la LED (voir checklist).
- **Phase 3** : envoie tour à tour les codes candidats (HDMI1/2/3/4 MSB+LSB, Source toggle)
  et te demande à chaque fois si la TV a basculé → identifie le bon code sans régénérer.

#### Générer les fichiers définitifs

Le **nom du candidat gagnant** te dit tout : `_lsb` dans le nom → ajouter `--lsb` ;
`_msb` → pas de flag. Le code hex = celui affiché par le script pour ce candidat.

**Cas MSB** (`HDMI1_msb` / `HDMI2_msb` ont basculé la TV) — sans flag :
```bash
python3 /opt/presence_tv/samsung_ir_gen.py 0xE0E09768 | sudo tee /opt/presence_tv/ir/hdmi1.txt
python3 /opt/presence_tv/samsung_ir_gen.py 0xE0E0D728 | sudo tee /opt/presence_tv/ir/hdmi2.txt
```

**Cas LSB** (`HDMI1_lsb` / `HDMI2_lsb` ont gagné) — avec `--lsb` :
```bash
python3 /opt/presence_tv/samsung_ir_gen.py --lsb 0xE0E09768 | sudo tee /opt/presence_tv/ir/hdmi1.txt
python3 /opt/presence_tv/samsung_ir_gen.py --lsb 0xE0E0D728 | sudo tee /opt/presence_tv/ir/hdmi2.txt
```

**Cas mixte** (ex: HDMI1 msb mais HDMI2 lsb) — flag par fichier :
```bash
python3 /opt/presence_tv/samsung_ir_gen.py 0xE0E09768 | sudo tee /opt/presence_tv/ir/hdmi1.txt
python3 /opt/presence_tv/samsung_ir_gen.py --lsb 0xE0E0D728 | sudo tee /opt/presence_tv/ir/hdmi2.txt
```

Vérifier + appliquer :
```bash
wc -l /opt/presence_tv/ir/hdmi1.txt    # >60 lignes = OK (pas vide / pas que des #)
sudo systemctl restart presence-tv
journalctl -fu presence-tv             # 'Switch TV -> HDMI 1' SANS ligne 'IR erreur'
```

#### Pérenniser dans le repo

Sinon au prochain flash SD tu retombes sur les placeholders. Depuis `~/presencePi` sur le Pi :
```bash
cp /opt/presence_tv/ir/hdmi1.txt /opt/presence_tv/ir/hdmi2.txt ir/
git add ir/hdmi1.txt ir/hdmi2.txt
git commit -m "feat: codes IR Samsung validés (HDMI1/HDMI2)"
git push
```

**Checklist on-site (gestes) :**
- [ ] Caméra **SELFIE** (la frontale ; l'arrière filtre souvent l'IR → flash invisible).
- [ ] LED émettrice à ~2 cm de l'objectif → flash **violet/blanc** = émission OK.
- [ ] Pour l'essai TV : module en **ligne directe** vers le récepteur IR de la TV, 1–2 m.
- [ ] TV pré-réglée sur une entrée **connue** (ex: HDMI2) pour voir la bascule.
- [ ] Si aucun code candidat ne marche → capturer depuis la télécommande **BN59-01259B**
      (récepteur IR sur GPIO18 requis, cf. 7.3 §2).

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

### 9.1 Monitoring (heartbeat / silence / watchdog)

Le service émet désormais des logs de santé en plus des switchs :
- **Heartbeat** toutes `heartbeat_s` (défaut 60s) :
  `alive — input=1 présence=True silence=0.1s` → preuve de vie + état courant.
- **Silence UART** : si aucune trame LD2450 reçue depuis `uart_silence_s` (défaut 5s) →
  `WARNING: Aucune trame LD2450 depuis Ns — capteur muet ?` (capteur débranché/mort).
  Au retour des trames : `LD2450 — trames de nouveau reçues.`
- **Watchdog systemd** (`WatchdogSec=30` + `Type=notify`) : si la boucle fige >30s,
  systemd tue et relance le service (le `Restart=always` ne couvrait que les crashs, pas les freezes).

Réglages dans `presence_tv.ini`, section `[monitor]` :
```ini
[monitor]
heartbeat_s = 60
uart_silence_s = 5
```

Tests rapides :
```bash
journalctl -fu presence-tv                 # voir "alive" toutes les 60s
# débrancher le capteur → WARNING "capteur muet" doit apparaître < 5s, rebrancher → "de nouveau reçues"
systemctl status presence-tv               # rester "active (running)" > 1 min = watchdog OK (pas de timeout notify)
```

✅ Heartbeat visible, silence détecté, service stable >1 min (watchdog pinge bien).

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
| Permission denied UART/lirc | `presence` pas dans `dialout`/`video`, OU ttyAMA0 en `root:tty 600` → règle udev + mask getty (cf. 3.2) |
| Service redémarre en boucle (~30s) | watchdog : `READY=1` jamais envoyé (port KO au boot) ou boucle figée — voir `journalctl` |
| WARNING "capteur muet" permanent | capteur débranché/mort, TX/RX inversés, ou baud — cf. Phase 6 |
