---
name: handsoff-core
description: Core knowledge for working with HandsOff
---

## Locale Configuration

The `-loc` flag bakes locales into the image at build time. The first locale is the primary language. Any standard BCP 47 locale can be used — add as many as needed, comma-separated.

To change locales at runtime:

```bash
adb shell settings put system system_locales en-US,ko-KR,ja-JP
```

The change takes effect immediately. Gboard (included via MindTheGapps) supports input for many languages out of the box.
