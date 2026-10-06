#!/bin/zsh
# The macOS release of ASTRA (Apple Silicon, macOS 14 or later): the Shipping build with the crew's mind and uv inside the app, signed with a
# Developer ID (hardened runtime, secure timestamp), notarized by Apple and stapled, then zipped as one file for a GitHub release (under 2 GiB).
#
#   tools/release_mac.sh <version> [--skip-build] [--no-notarize]
#
# The signing identity and the App Store Connect API key are read from .release.env (ignored by git) or from the environment:
#   ASTRA_SIGN_IDENTITY   "Developer ID Application: <name> (<team>)", in the login keychain
#   ASTRA_NOTARY_KEY      the .p8 file of an App Store Connect API key; ASTRA_NOTARY_KEY_ID, ASTRA_NOTARY_ISSUER: its key id and issuer id
# Nothing secret is printed or put in the app: the script fails if a key file, or the OpenRouter key of this checkout, is found in it.
# Log: Saved/Logs/release_mac.log. Output: Packaged/Release/ASTRA-<version>-macOS-AppleSilicon.zip (and its .sha256).
set -eo pipefail
cd "$(dirname "$0")/.."
VER="$1"
[[ -z "$VER" || "$VER" == --* ]] && { echo "usage: tools/release_mac.sh <version> [--skip-build] [--no-notarize]"; exit 2; }
shift
SKIP_BUILD=0
NOTARIZE=1
for a in "$@"; do
  case "$a" in
    --skip-build) SKIP_BUILD=1 ;;
    --no-notarize) NOTARIZE=0 ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done
[[ -f .release.env ]] && source ./.release.env
[[ -n "$ASTRA_SIGN_IDENTITY" ]] || { echo "no signing identity (ASTRA_SIGN_IDENTITY, .release.env)"; exit 1; }
security find-identity -v -p codesigning | grep -qF "$ASTRA_SIGN_IDENTITY" || { echo "the signing identity is not in the keychain"; exit 1; }
if (( NOTARIZE )); then
  [[ -f "$ASTRA_NOTARY_KEY" && -n "$ASTRA_NOTARY_KEY_ID" && -n "$ASTRA_NOTARY_ISSUER" ]] || { echo "no notarization key (ASTRA_NOTARY_*, .release.env)"; exit 1; }
fi
OUT="$PWD/Packaged/Release"
LOG="$PWD/Saved/Logs/release_mac.log"
mkdir -p "$OUT" Saved/Logs
: > "$LOG"
step() { print -P "%F{cyan}== $1%f"; print "== $1" >> "$LOG"; }
fail() { print -P "%F{red}$1%f (log: $LOG)"; exit 1; }

# 1. the Shipping app: build, cook, package, the mind's sources inside (tools/pacchetto.sh)
if (( ! SKIP_BUILD )); then
  step "build (Shipping)"
  tools/pacchetto.sh shipping >> "$LOG" 2>&1 || fail "the Shipping build failed"
  tail -1 "$LOG"
fi
SRC=$(find Packaged/Mac -maxdepth 2 -name "*.app" -type d | head -1)
[[ -d "$SRC" ]] || fail "no app in Packaged/Mac"
[[ -f "$SRC/Contents/Resources/mind/pyproject.toml" && -d "$SRC/Contents/Resources/mind/astra_mind" ]] || fail "the crew's mind is not inside $SRC"
APP="$OUT/ASTRA.app"
rm -rf "$APP"
ditto "$SRC" "$APP"
# Keep the signed bundle’s public version in sync with the release tag.
ASTRA_RELEASE_NUM=${VER%%-*}
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $ASTRA_RELEASE_NUM" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $ASTRA_RELEASE_NUM" "$APP/Contents/Info.plist"

# 2. what travels with the game: uv (the crew's Python environment is made with it on the first start, in Application Support), with its licence
step "uv inside the app"
UV=$(command -v uv) || fail "uv not found"
mkdir -p "$APP/Contents/Resources/mind/bin"
cp -f "$UV" "$APP/Contents/Resources/mind/bin/uv"
chmod 755 "$APP/Contents/Resources/mind/bin/uv"
cp -f tools/release/uv-LICENSE-MIT "$APP/Contents/Resources/mind/bin/uv.LICENSE"
print "uv $("$APP/Contents/Resources/mind/bin/uv" --version | cut -d' ' -f2)" | tee -a "$LOG"
# (nothing of a run may be inside: bytecode caches, a virtual environment, editor leftovers)
find "$APP/Contents/Resources/mind" \( -name "__pycache__" -o -name ".venv" -o -name ".DS_Store" -o -name "*.pyc" \) -prune -exec rm -rf {} + 2>/dev/null || true

# 3. nothing private goes out: no key file of any kind, and not the OpenRouter key of this checkout, anywhere in the app
step "no secrets in the app"
if find "$APP" \( -name ".env" -o -name "*.env" -o -name ".env.*" -o -name "*.p8" -o -name "*.p12" -o -name "*.pem" -o -name "*.key" \) | grep -q .; then
  fail "a key file is in the app"
fi
if [[ -f .env ]]; then
  # every value of this checkout's .env (the OpenRouter key, the asset sites' tokens), compared without ever being printed
  while IFS='=' read -r KEYNAME KEYVAL; do
    KEYVAL=${KEYVAL//\"/}
    [[ "$KEYNAME" == \#* || ${#KEYVAL} -lt 12 ]] && continue
    if grep -rlaF -- "$KEYVAL" "$APP" >/dev/null 2>&1; then
      fail "the value of $KEYNAME (.env) is inside the app"
    fi
  done < .env
  unset KEYNAME KEYVAL
fi
if grep -rlaE -- "sk-or-v1-[0-9a-f]{20,}" "$APP" >/dev/null 2>&1; then
  fail "an OpenRouter key is inside the app"
fi
print "clean" | tee -a "$LOG"

# 4. sign: every Mach-O file inside first (the engine's libraries, uv, the speech helper), then the app with its entitlements
step "sign (Developer ID, hardened runtime)"
N=0
while IFS= read -r -d '' f; do
  [[ "$f" == "$APP/Contents/MacOS/"* ]] && continue            # (the main executable is signed with the app)
  if file -b "$f" | grep -q "Mach-O"; then
    codesign --force --options runtime --timestamp --sign "$ASTRA_SIGN_IDENTITY" "$f" >> "$LOG" 2>&1 || fail "could not sign $f"
    N=$((N + 1))
  fi
done < <(find "$APP/Contents" -type f \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \) -print0)
codesign --force --options runtime --timestamp --entitlements Build/Mac/Resources/ASTRA.entitlements --sign "$ASTRA_SIGN_IDENTITY" "$APP" >> "$LOG" 2>&1 \
  || fail "could not sign the app"
codesign --verify --deep --strict --verbose=2 "$APP" >> "$LOG" 2>&1 || fail "the signature does not verify"
print "signed: $N inner files and the app" | tee -a "$LOG"

# 5. notarize (Apple checks a zip of the app), staple the ticket to the app, check Gatekeeper's verdict
if (( NOTARIZE )); then
  step "notarize (this uploads the app to Apple: minutes)"
  SUB="$OUT/notarize.zip"
  rm -f "$SUB"
  ditto -c -k --keepParent "$APP" "$SUB"
  xcrun notarytool submit "$SUB" --key "$ASTRA_NOTARY_KEY" --key-id "$ASTRA_NOTARY_KEY_ID" --issuer "$ASTRA_NOTARY_ISSUER" \
    --wait --timeout 3h --output-format json > "$OUT/notary.json" 2>> "$LOG" || true
  cat "$OUT/notary.json" >> "$LOG"
  STATUS=$(/usr/bin/python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('status',''))" "$OUT/notary.json" 2>/dev/null || true)
  ID=$(/usr/bin/python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('id',''))" "$OUT/notary.json" 2>/dev/null || true)
  rm -f "$SUB"
  if [[ "$STATUS" != "Accepted" ]]; then
    [[ -n "$ID" ]] && xcrun notarytool log "$ID" --key "$ASTRA_NOTARY_KEY" --key-id "$ASTRA_NOTARY_KEY_ID" --issuer "$ASTRA_NOTARY_ISSUER" "$OUT/notary_log.json" >> "$LOG" 2>&1
    fail "notarization: ${STATUS:-no answer} (Apple's log: $OUT/notary_log.json)"
  fi
  print "accepted ($ID)" | tee -a "$LOG"
  xcrun stapler staple "$APP" >> "$LOG" 2>&1 || fail "could not staple the ticket"
  xcrun stapler validate "$APP" >> "$LOG" 2>&1 || fail "the stapled ticket does not validate"
  spctl -a -vvv -t exec "$APP" >> "$LOG" 2>&1 || fail "Gatekeeper rejects the app"
  grep -E "source=|origin=" "$LOG" | tail -2
fi

# 6. the release file: one zip of the stapled app, under GitHub's 2 GiB a file
step "zip"
ZIP="$OUT/ASTRA-$VER-macOS-AppleSilicon.zip"
rm -f "$ZIP" "$ZIP.sha256"
ditto -c -k --keepParent "$APP" "$ZIP"
BYTES=$(stat -f %z "$ZIP")
(( BYTES < 2147483648 )) || fail "the zip is $((BYTES / 1048576)) MB: over GitHub's 2 GiB a file"
(cd "$OUT" && shasum -a 256 "$(basename "$ZIP")" > "$(basename "$ZIP").sha256")
print -P "%F{green}ready: $ZIP ($((BYTES / 1048576)) MB)%f"
