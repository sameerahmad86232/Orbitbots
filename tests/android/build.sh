#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bt="${ANDROID_BUILD_TOOLS:-$ANDROID_SDK_ROOT/build-tools/35.0.0}"
platform="${ANDROID_PLATFORM_JAR:-$ANDROID_SDK_ROOT/platforms/android-35/android.jar}"
mkdir -p tests/android/build/classes
"$bt/aapt2" link -o tests/android/build/base.apk --manifest tests/android/AndroidManifest.xml -I "$platform"
java com.sun.tools.javac.Main -source 8 -target 8 -bootclasspath "$platform:$bt/core-lambda-stubs.jar" -d tests/android/build/classes src/in/orbitai/mobile/{Store,Sync,Workbook}.java tests/android/src/in/orbitai/mobile/Harness.java
mapfile -t classes < <(find tests/android/build/classes -name '*.class')
"$bt/d8" --lib "$platform" --min-api 26 --output tests/android/build/dex.zip "${classes[@]}"
python3 - <<'PY'
from zipfile import ZipFile
with ZipFile('tests/android/build/base.apk','a') as a,ZipFile('tests/android/build/dex.zip') as d:
 for n in d.namelist():a.writestr(n,d.read(n))
PY
"$bt/zipalign" -f 4 tests/android/build/base.apk tests/android/build/aligned.apk
export ORBIT_TEST_SIGNING_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
rm -f tests/android/build/test.jks
keytool -genkeypair -keystore tests/android/build/test.jks -storepass:env ORBIT_TEST_SIGNING_PASSWORD -keypass:env ORBIT_TEST_SIGNING_PASSWORD -alias test -dname 'CN=Ephemeral Orbit Test' -keyalg RSA -keysize 2048 -validity 1 >/dev/null 2>&1
"$bt/apksigner" sign --ks tests/android/build/test.jks --ks-key-alias test --ks-pass env:ORBIT_TEST_SIGNING_PASSWORD --out tests/android/build/harness.apk tests/android/build/aligned.apk
