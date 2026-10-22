Orbit Bot 2.0 adds configurable model-provider connections, OpenAI-compatible presets, Ollama server support, public HTTPS page extraction/crawling using jsoup, private text knowledge imports/search, file previews, new role templates, and a redesigned mobile UI.

Download **Orbit-Bots-2.0.apk** below and open it on Android 8.0 or later. In Settings, save a connection first, then enter its API key (not required for an unauthenticated Ollama server), choose an available model and save task settings. For Ollama on a separate device, use that device's LAN address; localhost means the phone itself.

The APK does not bundle Ollama or model weights. PDF attachment support is currently xAI-only; vision and tool calling depend on the chosen model. Arbitrary proprietary API protocols, cloud computers, 24/7 hosting, connected inboxes, payments and image/video generation are not included. See README for the feature list and limits.

Verification: Android compilation and APK signature verification passed. Local HTTP provider contract tests and mocked-native mobile UI tests passed. Real Android installation, live paid-provider requests and actual Ollama inference have not been verified here. No signing credentials or real API keys are shipped in source.
