#!/usr/bin/env bash
# Test IR "clé en main" à exécuter SUR PLACE devant la TV.
# Trois phases : diagnostic émetteur -> boucle caméra -> essai séquentiel des codes.
#
# Usage :
#   sudo ./tools/ir_onsite.sh                 # tout, device /dev/lirc0
#   sudo ./tools/ir_onsite.sh --device /dev/lirc0
#   sudo ./tools/ir_onsite.sh --loop-only     # seulement la boucle caméra (phase 2)
#   sudo ./tools/ir_onsite.sh --try-only      # seulement l'essai TV (phase 3)
set -euo pipefail

DEVICE=/dev/lirc0
MODE=all

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device) DEVICE="$2"; shift 2 ;;
    --loop-only) MODE=loop; shift ;;
    --try-only) MODE=try; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Argument inconnu : $1" >&2; exit 1 ;;
  esac
done

# Localiser le générateur (déployé ou depuis le repo)
GEN=/opt/presence_tv/samsung_ir_gen.py
[[ -f "$GEN" ]] || GEN="$(dirname "$0")/../src/samsung_ir_gen.py"
[[ -f "$GEN" ]] || { echo "samsung_ir_gen.py introuvable" >&2; exit 1; }

CAND_DIR="$(mktemp -d /tmp/ir_candidates.XXXXXX)"
trap 'rm -rf "$CAND_DIR"' EXIT

# Codes candidats Samsung (séries MU/NU/KU). nom|code_hex|flag
# Si la TV ne bascule pas avec MSB, les variantes --lsb couvrent l'autre ordre de bits.
CANDIDATES=(
  "HDMI1_msb|0xE0E09768|"
  "HDMI1_lsb|0xE0E09768|--lsb"
  "HDMI2_msb|0xE0E0D728|"
  "HDMI2_lsb|0xE0E0D728|--lsb"
  "HDMI3_msb|0xE0E043BC|"
  "HDMI4_msb|0xE0E0A45B|"
  "SOURCE_toggle|0xE0E0807F|"
)

gen_candidate() {  # $1=nom $2=code $3=flag -> écrit $CAND_DIR/$1.txt
  python3 "$GEN" $3 "$2" > "$CAND_DIR/$1.txt"
}

phase_diag() {
  echo "=== Phase 1 — Diagnostic émetteur ($DEVICE) ==="
  if [[ ! -e "$DEVICE" ]]; then
    echo "  ✗ $DEVICE absent → overlay gpio-ir-tx manquant (config.txt) ou pas reboot."
    exit 1
  fi
  echo "  - Capacités :"
  if ir-ctl -d "$DEVICE" --features 2>/dev/null | grep -qi send; then
    echo "    ✓ SEND supporté"
  else
    echo "    ✗ SEND absent → mauvais device ou overlay RX au lieu de TX"
  fi
  echo "  - Overlay noyau :"
  dmesg 2>/dev/null | grep -i 'gpio-ir' | tail -2 | sed 's/^/    /' || echo "    (rien dans dmesg)"
  echo
}

phase_loop() {
  echo "=== Phase 2 — Boucle d'émission (caméra) ==="
  echo "  Filme la LED émettrice du module IR avec la caméra SELFIE (la LED IR"
  echo "  est invisible à l'œil nu ; flash violet/blanc visible seulement caméra)."
  echo "  Beaucoup de caméras ARRIÈRE filtrent l'IR → utilise la frontale."
  gen_candidate HDMI1_msb 0xE0E09768 ""
  echo "  Envoi de HDMI1 en boucle pendant 20 s (Ctrl+C pour couper)..."
  local end=$((SECONDS + 20))
  while (( SECONDS < end )); do
    ir-ctl -d "$DEVICE" --send="$CAND_DIR/HDMI1_msb.txt" || true
    sleep 0.4
  done
  echo "  Vu un flash violet à la caméra ? (o/n)"
  read -r seen
  if [[ "$seen" == "o" ]]; then
    echo "    ✓ Émission OK → le problème éventuel est le CODE (Phase 3) ou l'orientation."
  else
    echo "    ✗ Aucun flash → hardware : VCC sur 5V (pin4) ? DAT sur GPIO17 (pin11) ? GND ?"
    echo "      Ou mauvaise caméra (refais avec la frontale)."
  fi
  echo
}

phase_try() {
  echo "=== Phase 3 — Essai séquentiel sur la TV ==="
  echo "  Mets la TV sur une entrée CONNUE (ex: HDMI2 manuel), pointe le module"
  echo "  vers le récepteur IR de la TV (1–2 m, ligne directe). Observe l'écran."
  echo
  for entry in "${CANDIDATES[@]}"; do
    IFS='|' read -r name code flag <<< "$entry"
    gen_candidate "$name" "$code" "$flag"
    read -r -p "  → Tester $name ($code ${flag:-msb}) ? [Entrée=envoyer, s=skip] " ans
    [[ "$ans" == "s" ]] && { echo "    skip"; continue; }
    ir-ctl -d "$DEVICE" --send="$CAND_DIR/$name.txt" || true
    sleep 0.3
    ir-ctl -d "$DEVICE" --send="$CAND_DIR/$name.txt" || true   # double envoi (Samsung MU)
    read -r -p "    La TV a basculé ? [o/n] " ok
    if [[ "$ok" == "o" ]]; then
      echo "    ✓✓ TROUVÉ : $name = $code ${flag:-msb}"
      echo "    → déploie ce code : python3 $GEN $flag $code | sudo tee /opt/presence_tv/ir/<hdmiX>.txt"
    fi
  done
  echo
  echo "  Note les codes gagnants HDMI1 + HDMI2, puis génère les fichiers définitifs."
}

case "$MODE" in
  all)  phase_diag; phase_loop; phase_try ;;
  loop) phase_loop ;;
  try)  phase_try ;;
esac
