# Fonts

The repository does not ship a font: they are large, and which one you want
depends on the target language and the look you are after.

You need a font that covers the glyphs of your **target** language, otherwise the
renderer draws empty boxes. Point `engine.mit.font` at the file:

```yaml
engine:
  mit:
    font: ./fonts/SourceHanSansSC-Bold.otf
```

Good choices, all freely redistributable:

| font | covers | where |
|---|---|---|
| Source Han Sans / Noto Sans CJK | Simplified Chinese, Traditional, Japanese, Korean | https://github.com/adobe-fonts/source-han-sans |
| Source Han Serif / Noto Serif CJK | same, serif | https://github.com/adobe-fonts/source-han-serif |
| Noto Sans | Latin, Cyrillic, Greek | https://fonts.google.com/noto |

Put the `.otf`/`.ttf` in this folder (it is git-ignored, so your copy never gets
committed) or anywhere else on disk — the config takes a path, not a name.

Tip: bold weights read better over artwork at small sizes, which is why the
examples point at a `-Bold` file.
