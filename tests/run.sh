#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tests/lib tests/out
if [[ ! -f tests/lib/json.jar ]]; then curl -fsSL https://repo.maven.apache.org/maven2/org/json/json/20240303/json-20240303.jar -o tests/lib/json.jar; fi
java com.sun.tools.javac.Main -classpath tests/lib/json.jar:libs/jsoup-1.18.3.jar -d tests/out tests/stubs/android/content/Context.java tests/stubs/in/orbitai/mobile/*.java src/in/orbitai/mobile/Provider.java src/in/orbitai/mobile/WebTools.java tests/java/in/orbitai/mobile/*.java
java -cp tests/out:tests/lib/json.jar:libs/jsoup-1.18.3.jar in.orbitai.mobile.ProviderContractTest
