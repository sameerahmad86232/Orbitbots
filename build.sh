#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${ANDROID_BUILD_TOOLS:=${ANDROID_SDK_ROOT:-}/build-tools/35.0.0}"
: "${ANDROID_PLATFORM_JAR:=${ANDROID_SDK_ROOT:-}/platforms/android-35/android.jar}"
if [[ ! -x "$ANDROID_BUILD_TOOLS/aapt2" || ! -f "$ANDROID_PLATFORM_JAR" ]]; then
 echo 'Set ANDROID_SDK_ROOT, or ANDROID_BUILD_TOOLS and ANDROID_PLATFORM_JAR (API 35).'; exit 1
fi
mkdir -p build/classes
node --check assets/app.js
"$ANDROID_BUILD_TOOLS/aapt2" compile --dir res -o build/resources.zip
"$ANDROID_BUILD_TOOLS/aapt2" link -o build/unsigned.apk --manifest AndroidManifest.xml -I "$ANDROID_PLATFORM_JAR" -A assets build/resources.zip
java com.sun.tools.javac.Main -source 8 -target 8 -bootclasspath "$ANDROID_PLATFORM_JAR:$ANDROID_BUILD_TOOLS/core-lambda-stubs.jar" -classpath "libs/jsoup-1.18.3.jar" -d build/classes src/in/orbitai/mobile/*.java
mapfile -t orbit_classes < <(find build/classes -name '*.class')
"$ANDROID_BUILD_TOOLS/d8" --lib "$ANDROID_PLATFORM_JAR" --min-api 26 --output build/dex.zip "${orbit_classes[@]}" libs/*.jar
python3 - <<'PY'
from zipfile import ZipFile, ZIP_DEFLATED
with ZipFile('build/unsigned.apk','a',ZIP_DEFLATED) as apk,ZipFile('build/dex.zip') as dex:
 for name in dex.namelist(): apk.writestr(name,dex.read(name))
PY
"$ANDROID_BUILD_TOOLS/zipalign" -f -p 4 build/unsigned.apk build/aligned.apk
if [[ -n "${ORBIT_SIGNING_STORE:-}" && -n "${ORBIT_SIGNING_PASSWORD:-}" ]]; then
 "$ANDROID_BUILD_TOOLS/apksigner" sign --ks "$ORBIT_SIGNING_STORE" --ks-key-alias orbit --ks-pass env:ORBIT_SIGNING_PASSWORD --key-pass env:ORBIT_SIGNING_PASSWORD --out build/Orbit-Bots.apk build/aligned.apk
 "$ANDROID_BUILD_TOOLS/apksigner" verify --verbose build/Orbit-Bots.apk
else
 echo 'Built aligned unsigned APK. Set ORBIT_SIGNING_STORE and ORBIT_SIGNING_PASSWORD to sign.'
fi
