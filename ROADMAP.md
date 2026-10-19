# Roadmap

This repository is the **lean core** on purpose. This file records what is in it,
what a fuller build adds, and why the split exists — so nobody has to guess
whether a missing feature is an oversight or a decision.

## In the lean core (0.1.x)

- one folder per book, resumable batch runs with per-book state
- source adapters: local folders, or gallery-dl (any site it supports)
- translation backends: anything manga-image-translator accepts, chosen by config
- prompt and dictionary files kept outside the code
- engine output (lossless PNG) and delivery format (WebP q95) as separate steps
- `doctor`, `run`, `translate`, `download`, `status`, `compare`, `compress`
- side-by-side preview sheets, so quality is checked with eyes not numbers

## What a fuller build (0.2+) adds

These are the pieces the author runs locally and that were deliberately left out
of 0.1.x. They are listed here as committed intentions, not promises about order.

### Intake quality of life

- **Clipboard watcher.** A background watcher that notices a page or gallery URL
  copied to the clipboard, appends it to the queue, and reports what it added.
  The point is that collecting material stops requiring a text editor.
- **Link normalisation and de-duplication.** Canonicalise pasted URLs (strip
  tracking parameters and per-session noise), recognise the same item reached via
  different URL forms, and skip anything already queued or already downloaded.
  Without this, a clipboard-driven queue fills with near-duplicates within a day.
- **Queue file with explicit states.** A plain text or JSON queue where each entry
  is pending / downloading / done / failed, so intake and processing can run at
  different times and a failure is visible rather than silently dropped.

### Throughput

- **Concurrency.** Several books in flight at once, with per-book locks so a book
  is never processed twice.
- **Resource arbitration.** Optionally wait for a GPU to be free before starting,
  and hand the GPU back after each book, so this does not fight Blender, ComfyUI
  or a game render for the card. Needs a small lock protocol shared with whatever
  else is running.
- **Quiet hours and yielding.** Start work only inside a time window; yield when a
  higher-priority job appears.

### Operations

- **Local dashboard.** A single page showing per-book progress, live log tail,
  passed/failed counts, and start/stop for each worker. Read-only views are the
  easy part; start/stop needs the process supervision below.
- **Supervisor.** Restart a worker that died, record why it died, and never let a
  killed job masquerade as finished.

### Sources

- Additional adapters: direct download links, RSS/feeds, network shares, and a
  "watched folder" mode for material that arrives as archives.

## Why the split

`0.1.x` is sized to be read end to end in an afternoon, and every piece of it is
exercised by the test suite. The list above is where the author's actual daily
workflow lives — and it is also where the machine-specific assumptions accumulate
(paths, ports, a particular GPU, a particular desktop). Shipping it as a second
release keeps both promises: the lean core stays supportable, and the throughput
work stays available to people who need it, with its assumptions written down
instead of implied.

If you are choosing today: start here. Get one book through `mscan run` and look
at it with `mscan compare`. The scheduling machinery only pays for itself once
the output quality is where you want it.
