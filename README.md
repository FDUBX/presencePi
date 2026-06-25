# presencePi — Détecteur de présence → contrôle input TV

Raspberry Pi Zero 2W + LD2450 (mmWave 24 GHz) + module IR Haljia 38 kHz
→ bascule l'entrée d'une **Samsung UE55MU6170** selon la présence.

| Condition | Action |
|-----------|--------|
| Présence détectée | TV → HDMI 1 |
| Absence > `timeout_s` | TV → HDMI 2 |

```
LD2450 (UART 256000) → Pi Zero 2W → module IR Haljia → Samsung UE55MU6170
                          presence_tv.py (présence → HDMI1 / absence → HDMI2)
```

## Arborescence

```
src/presence_tv.py      Service principal (lecture LD2450 + envoi IR)
src/samsung_ir_gen.py   Génère les fichiers raw ir-ctl depuis un code hex
config/presence_tv.ini  Configuration (port, baud, zone, timeout, IR)
config/config.txt.snippet  Overlays /boot (UART PL011 + IR TX)
ir/hdmi1.txt, hdmi2.txt Trames IR (à générer/valider)
systemd/presence-tv.service
install.sh              Déploiement sur le Pi
```

## BOM

| Composant | Référence | Prix |
|-----------|-----------|------|
| Raspberry Pi Zero 2W | Barium Electronics | 44,90 € |
| Capteur mmWave | HiCOZZIE HLK-LD2450 | 10,89 € |
| Module IR émetteur | Haljia 38 kHz | 7,99 € |
| Câbles Dupont F-F 3 broches | Fasizi 70 cm | 6,99 € |
| Câbles Dupont 120 pcs | ELEGOO 20 cm | 8,54 € |
| micro SD 16 Go | KEXIN Class 10 A1 | 10,99 € |
| Boîtier alu | eleUniverse Pi Zero | 8,51 € |
| Chargeur micro USB | DBZYLN 5V | 8,99 € |

> Module Haljia = LED 940 nm + driver intégrés. Aucun transistor/LED discret requis.
> Module = **émetteur pur** : capturer des codes IR exige un récepteur séparé (TSOP1738 / KY-022).

## Câblage

### LD2450 → Pi (UART)
```
LD2450 TX  → GPIO15 (RXD) — pin 10
LD2450 RX  → GPIO14 (TXD) — pin 8
LD2450 VCC → 5V           — pin 2
LD2450 GND → GND          — pin 6
```

### Module IR Haljia → Pi
Pinout module : (1) DAT — (2) VCC — (3) GND
```
Haljia VCC (2) → 5V     — pin 4
Haljia GND (3) → GND    — pin 14
Haljia DAT (1) → GPIO17 — pin 11
```
> VCC **doit** être 5V. DAT compatible 3.3V GPIO → connexion directe.

## Installation

1. **OS** : Raspberry Pi OS Lite 64-bit (headless via Raspberry Pi Imager : hostname `presence-tv`, SSH, Wi-Fi).
2. **Overlays** : ajouter `config/config.txt.snippet` à `/boot/firmware/config.txt`, puis :
   ```bash
   sudo systemctl disable hciuart
   sudo reboot
   ```
3. **Console série** : `sudo raspi-config` → Interface → Serial Port → login shell **No**, hardware **Yes**.
4. **Déploiement** : depuis la racine du repo, sur le Pi :
   ```bash
   sudo ./install.sh
   ```
5. **Codes IR** : voir [Codes IR Samsung](#codes-ir-samsung).
6. **Démarrer** :
   ```bash
   sudo systemctl start presence-tv
   journalctl -fu presence-tv
   ```

## Protocole LD2450

Trame de sortie (mode cible), **30 octets**, ~30 trames/s :
```
AA FF 03 00 | cible1(8o) cible2(8o) cible3(8o) | 55 CC
```
- **3 cibles max** (pas 4). Chaque cible : x(2o) y(2o) speed(2o) res(2o), little-endian.
- **Coordonnées en signe+magnitude** : bit 15 = signe (set → positif), bits 0-14 = magnitude en mm.
  PAS de complément à deux → décodage dédié dans `_decode_coord()`. Une lecture `int16` naïve donne des coordonnées fausses.
- Présence = au moins une cible avec `res > 0`.
- Débit : **256000 baud** (non standard) → exige le PL011 (`ttyAMA0`), pas le mini-UART (`ttyS0`)
  dont la vitesse dépend de l'horloge CPU et décroche à haut débit.

## Codes IR Samsung

Protocole Samsung (variante NEC, 38 kHz, leader 4500/4500 µs, payload 32 bits).

**Générer les trames** (codes discrets documentés séries MU/NU/KU) :
```bash
python3 src/samsung_ir_gen.py 0xE0E09768 > ir/hdmi1.txt   # HDMI1
python3 src/samsung_ir_gen.py 0xE0E0D728 > ir/hdmi2.txt   # HDMI2 (à confirmer)
```

**À valider sur la TV** :
- Si pas de réaction → réessayer LSB-first : `--lsb`.
- Caveat connu : certains modèles renvoient « Not Available » sur le code discret HDMI2+.
- Méthode la plus fiable : capturer depuis la télécommande **BN59-01259B** (récepteur IR requis,
  overlay `gpio-ir` sur GPIO18) : `ir-ctl -d /dev/lirc1 --receive=ir/hdmi1.txt`.

**Vérifier l'émission** : pointer le module vers la caméra d'un smartphone → LED visible en violet.
```bash
ir-ctl -d /dev/lirc0 --send=ir/hdmi1.txt
```

## IR vs CEC

IR retenu (matériel en main, universel ; portée 1-2 m, alignement requis).
Le MU6170 supporte Anynet+ (CEC) — alternative future (nécessiterait un adaptateur USB-CEC,
le Pi Zero 2W n'ayant pas de sortie HDMI exploitable côté CEC).

## Points ouverts

| # | Point | Action |
|---|-------|--------|
| 1 | Codes IR HDMI1/HDMI2 | Générer + valider sur la TV (camera test), sinon capturer BN59-01259B |
| 2 | Double envoi IR (`repeat`) | Ajuster dans `presence_tv.ini` (1 ou 2) |
| 3 | Zone LD2450 | `[zone]` dans l'ini (désactivée par défaut) |
| 4 | Timeout absence | `timeout_s` (30 s par défaut) |
| 5 | Récepteur IR | Non fourni dans le BOM — requis seulement pour la capture |

## Références

- [HLK-LD2450 Serial Protocol v1.03](https://make.net.za/wp-content/datasheets/HLK%20LD2450%20Serial%20Communication%20Protocol%20v1.03.pdf)
- [Raspberry Pi UART — PL011 vs Mini UART](https://www.raspberrypi.org/documentation/configuration/uart.md)
- [Just Add Power — Samsung TV IR Control](https://justaddpower.happyfox.com/kb/article/481-samsung-tv-ir-control/)
