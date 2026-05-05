---
name: handsoff
description: Core knowledge for working with HandsOff — an MCP server that controls rooted Android devices over ADB. Covers locale configuration inline. Routes to bundled reference docs for heavier setup flows (KakaoTalk + Iris bot). Use whenever the user is operating a HandsOff device, configuring its locale, or asking to install/configure something on top of it.
---

# HandsOff

HandsOff exposes Android-device control as MCP tools (`app_install`, `adb_shell`, `push_file`, `expose_service`, `system_button`, `set_agent_keyboard`, etc.). This file is the entry point — it covers general device knowledge inline and points to bundled references for task-specific setups.

## Locale configuration

The `-loc` flag bakes locales into the image at build time. The first locale is the primary language. Any standard BCP 47 locale can be used — add as many as needed, comma-separated.

To change locales at runtime:

```bash
adb shell settings put system system_locales en-US,ko-KR,ja-JP
```

The change takes effect immediately. Gboard (included via MindTheGapps) supports input for many languages out of the box.

## Bundled references — read on demand

These files are NOT loaded into context up front. Read the matching one only when the user's task lands in its scope.

| File | Read when |
| ---- | --------- |
| [`references/kakaotalk-iris.md`](references/kakaotalk-iris.md) | User asks to install KakaoTalk + Iris bot framework on a HandsOff device, expose Iris through the reverse proxy, or verify an Iris install is healthy. Stops at "Iris is reachable and authenticated" — does not document Iris endpoint usage. |

When you decide a reference is in scope, read the whole file before acting on it. Don't quote excerpts from memory.

---

Contributing a new reference? See [CONTRIBUTING.md](CONTRIBUTING.md) and use the [`add-skill-reference` PR template](../../.github/PULL_REQUEST_TEMPLATE/add-skill-reference.md).
