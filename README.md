# manga-scanlation

**Point it at a folder of comic pages and get the same pages back in another
language: the original text is erased, the artwork behind it is restored, and the
translation is drawn back in.**

One folder is one book. Put twenty folders in, run one command, and walk away —
when you come back each folder has translated pages, ready to read. It is built
for people with a shelf of untranslated material and no patience for editing
speech bubbles one at a time.

After you have it installed, using it is three steps: drop your book folders into
`data/source/`, copy `config.example.yaml` to `config.yaml` and point it at your
translator, then run `mscan doctor` to catch setup problems and `mscan run` to
process everything that is not done yet. Rerunning `mscan run` is always safe: it
skips finished pages, so an interrupted night of processing resumes where it
stopped instead of starting over.

```bash
mscan doctor          # is my setup sane?
mscan run             # process every pending book
mscan compare         # one image per book: original next to translation
```

---

## What it actually does

For every page, four things happen in order:

1. **Find the text.** A detector locates every text region — dialogue in bubbles,
   sound effects painted straight onto the art, margin notes.
2. **Erase it.** An inpainting model wipes the text out and fills the hole with
   plausible background, so no ghost of the original lettering stays behind.
3. **Translate it.** The lines go to a language model (or DeepL, or Sakura, or a
   local model — your choice) with page context so pronouns and names stay
   consistent.
4. **Typeset it.** The translation is drawn back into the original text area,
   with the original alignment, an outline for readability, and a font size
   fitted to the box.

Everything is a folder of files on disk. There is no database, no server, no
state you cannot inspect with a file manager.

## What this repository is — and is not

This is the **lean core**: the pipeline, the configuration layer, the source
adapters and a few quality-of-life tools. It is deliberately small enough to read
end to end in an afternoon.

It does **not** include the machinery the original author runs on a dedicated
machine for a library in the thousands of books: multi-lane parallel schedulers,
a web dashboard with live progress, GPU arbitration between render jobs, or
overnight watchdogs. That code is specific to one machine's workflow and would be
hard to support honestly. A fuller version may follow as a separate release; if
it does, this repository stays the supported starting point, because a tool you
can debug beats a scheduler you cannot. Start here.

## Requirements

| | |
|---|---|
| Python | 3.10 or newer (this repository) |
| [manga-image-translator](https://github.com/zyddnys/manga-image-translator) | does the detection, OCR, inpainting and typesetting |
| A translation backend | any OpenAI-compatible endpoint, Ollama, Sakura, DeepL, Gemini, Groq, … |
| A CJK font | e.g. Source Han Sans, Noto Sans CJK |
| GPU | strongly recommended. CPU works but is slow |

manga-image-translator downloads its own model weights (a few hundred MB) on the
first run, plus a few GB if you use one of its offline translators.

## Install

```bash
git clone https://github.com/your-org/manga-scanlation
cd manga-scanlation
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e .
```

Then install manga-image-translator **next to it**, in its own environment:

```bash
git clone https://github.com/zyddnys/manga-image-translator vendor/manga-image-translator
cd vendor/manga-image-translator
python -m venv .venv        # keep its dependencies separate from ours
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

Two separate environments on purpose: manga-image-translator pins its own heavy
dependencies (torch, paddle, …) and mixing them with ours is a reliable way to
break both.

## Configure

```bash
cp config.example.yaml config.yaml
cp config/mit-config.example.json config/mit-config.json
cp config/gpt_config.example.yaml config/gpt_config.yaml
cp config/prompt/zh-CN.example.txt config/prompt/zh-CN.txt
```

`config.yaml` is wiring only — paths, which engine, which translator. Edit these
and nothing else:

```yaml
engine:
  mit:
    # interpreter of the environment you created for manga-image-translator
    python: ./vendor/manga-image-translator/.venv/bin/python
    root: ./vendor/manga-image-translator
    font: ./fonts/SourceHanSansSC-Bold.otf

translation:
  translator: openai            # any backend manga-image-translator supports
  target_lang: CHS              # CHS, CHT, ENG, JPN, KOR, ...
  model: qwen2.5:32b
  base_url: http://127.0.0.1:11434/v1
  api_key_env: OPENAI_API_KEY   # name of the variable holding the key
```

Quality knobs (mask width, font size offset, detector thresholds) live in
`config/mit-config.json`, which is manga-image-translator's own format, so there
is exactly one place to tune them. Every field is commented in the example file.

Output is a two-step thing. The engine only ever writes lossless PNG — upstream
allows lossy quality control for JPEG and nothing else — and a separate step turns
those into WebP at quality 95. `mscan run` does it automatically; `mscan compress`
does it on its own, and `output.compress: false` leaves the PNGs alone. The point
of the split is that no lossy image is ever fed into another lossy pass.

## Using it

```bash
# 1. put pages in place: one folder per book
cp -r ~/incoming/my-book data/source/

# 2. check the setup
mscan doctor

# 3. run
mscan run

# 4. look at the result before committing to a large batch
mscan compare --book my-book --pages 4
```

| command | what it does |
|---|---|
| `mscan doctor` | checks interpreter, model weights, font, dicts, endpoint, disk space |
| `mscan run` | download (if configured) → translate → report |
| `mscan translate` | translate only |
| `mscan download` | fetch pages only, via gallery-dl |
| `mscan compress` | convert finished PNG pages to the configured lighter format |
| `mscan status` | per-book progress table |
| `mscan compare` | side-by-side sheet: originals vs translations |
| `mscan config` | print the resolved configuration |
| `mscan run --dry-run` | print the exact engine command, run nothing |

Useful flags: `--only BOOK` to pick books, `--redo` to rebuild finished ones,
`--limit N` to stop after N books, `-v` for debug output.

## Choosing a translator

Nothing here is tied to one model. `translation.translator` is passed straight to
manga-image-translator, so its whole backend list is available:

- **Local and free** — `ollama` or `custom_openai` against Ollama, vLLM, LM Studio.
  Set `base_url`, `model`, and any non-empty key.
- **Any OpenAI-compatible API** — `openai` plus `base_url`. Works for hosted
  providers and company gateways alike.
- **Japanese→Chinese specialists** — `sakura`, if you have the model.
- **Classic MT** — `deepl`, `baidu`, `youdao`, `caiyun`.
- **Nothing at all** — `none` erases text and renders nothing; useful for testing
  the pipeline without burning model calls.

`translation.prompt` points at a plain text file whose contents become the system
prompt. `config/prompt/zh-CN.example.txt` is a working prompt for Simplified
Chinese; it is written for comic dialogue, and the two things it spends most of
its words on are the ones that actually matter in practice: *never compress the
translation*, and *fix OCR typos before translating*.

## Sources

Type `local` reads folders you already have. Type `gallerydl` shells out to
[gallery-dl](https://github.com/mikf/gallery-dl), which supports hundreds of
sites — nothing in this repository knows about any particular gallery. Put URLs
in `links.txt` (one per line) or in `source.gallerydl.urls`, and see
`config/gallery-dl.example.json` for a starting config.

If you need something else — an RSS feed, a DDL mirror, a scan of a bookshelf —
the seam is small: implement a function that puts pages into `data/source/<book>/`
and returns, and let the rest of the pipeline stay untouched.

## Tuning (lessons from real material)

The defaults are a starting point, not a universal answer. These four are the
ones that most often need attention, and each has a specific symptom:

| knob | in | symptom that means "change me" |
|---|---|---|
| `mask_dilation_offset` | `mit-config.json` | Faint halo or colour fringe left around where text used to be. Raise it until the glow is eaten. |
| `font_size_offset` | `mit-config.json` | Translation looks small with lots of empty space in the box. |
| `ocr.ignore_bubble` | `mit-config.json` | Only change if text *outside* bubbles is noise. **Raising this silently deletes dialogue** on comics where lines are painted on the art. |
| `context_size` | `config.yaml` | Names or pronouns drift between pages. |

Two settings in the defaults are there because the opposite is a trap:
`inpainting_precision: fp32` (half precision makes `torch.fft` fail on
non-power-of-two feature maps, and is slower even when it works) and
`disable_font_border: false` (the outline is what keeps replacement text legible
when inpainting was imperfect).

After changing anything, run `mscan translate --only BOOK --redo` on **one** book
and look at it with `mscan compare` before batching the rest.

## When something goes wrong

**Fewer output pages than input pages.** The run reports it as a failure rather
than pretending success. Just run it again: the engine skips pages that already
exist, so a rerun fills only the gaps.

**Text is missing that existed before.** Check `ocr.ignore_bubble` first — it is
the usual culprit. Then `filter_text`.

**Garbled or invented translations.** Lower `temperature`, and make sure the
prompt's line-count rule is present: the model must return one line per input
line, with the same numbering.

**A model echoed its reasoning onto the page.** A reasoning model wrapped its
answer in a scratch block. Add a `rgx_capture` that strips it (see
`config/gpt_config.example.yaml`), or use an instruct model.

**Boxes with square glyphs instead of characters.** The font is missing CJK
glyphs. Point `engine.mit.font` at a font that has them.

**Everything is slow.** You are probably on CPU. `mscan doctor` reports what it
found; a GPU is 10–30x faster for this workload.

## Scope and expectations

This is a translation aid, not a publisher. It produces a best-effort
translation — the prompt is good, the inpainting is good, and both still make
mistakes, especially on stylised lettering and OCR-hostile art. Read before you
distribute.

Nothing in this repository downloads anything unless you configure a source and
provide links. If you do configure one, respect the site's terms and rate limits,
and remember that the copyright in a comic belongs to its author: this tool is
for material you have the right to translate, and for private study.

## Credits

Standing on: [manga-image-translator](https://github.com/zyddnys/manga-image-translator)
(detection, OCR, inpainting, typesetting), [gallery-dl](https://github.com/mikf/gallery-dl)
(downloading), and the models those projects ship. The configuration defaults and
the prompt here encode hard-won lessons from running this pipeline over a real
library; the reasoning is kept in the config comments rather than in a wiki, so it
travels with the code.

## License

MIT. See [LICENSE](LICENSE).
