#!/bin/bash
set -euo pipefail
adb install -r downloads/Orbit-Bots-4.0.apk
adb logcat -c
adb shell am start -W -n in.orbitai.mobile/.MainActivity
sleep 4
adb shell dumpsys activity activities | grep -F 'in.orbitai.mobile/.MainActivity'
if adb logcat -d -s AndroidRuntime:E | grep -F 'FATAL EXCEPTION'; then exit 1; fi
adb exec-out screencap -p > tests/android/build/app-smoke.png
adb install -r tests/android/build/harness.apk
adb shell am start -W -n in.orbitai.tests/in.orbitai.mobile.Harness
for n in {1..45}; do
 result="$(adb shell run-as in.orbitai.tests cat files/result.txt 2>/dev/null || true)"
 if [[ "$result" == PASS:* ]]; then echo "$result"; exit 0; fi
 if [[ "$result" == FAIL:* ]]; then echo "$result"; exit 1; fi
 sleep 1
done
echo 'Native harness timed out'; exit 1
