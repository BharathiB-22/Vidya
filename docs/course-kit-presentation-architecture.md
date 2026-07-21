# Course Kit Presentations — Research & Architecture Proposal

**Status:** Phases 0 and 1 implemented (uncommitted). Phases 2-5 not started.
**Module:** M03 Course Kit · `backend/app/workers/heavy/course_kit_export.py`
**Date:** 2026-07-17

---

## 1. What we have today

`_generate_pptx()` in `course_kit_export.py` is ~700 lines of python-pptx driving
absolutely-positioned shapes. It is better than "basic": there is already a slide-type
registry, a tenant colour override, a cover slide, CO/schedule slides and seven
type-specific renderers (`OBJECTIVES`, `WORKED_EXAMPLE`, `CODE`, `COMMON_MISTAKES`,
`ACTIVITY`, `QUIZ`, `SUMMARY`).

Four findings matter more than anything in the tool survey below.

### 1.1 We already ask the AI for diagrams and then throw them away

`_SlideContentAI` has had `diagram_prompt` all along, and the prompt is specific about it:

> *"diagram_prompt: a specific, renderable diagram description — name the diagram type
> (flowchart / block diagram / sequence diagram / labelled architecture), list the…"*

`DIAGRAM` is in `_VALID_SLIDE_TYPES`. But `_SLIDE_REGISTRY` has **no `DIAGRAM` renderer**,
so every diagram slide falls through to `_render_generic` and is rendered as *bullet text*.
The PDF path prints the prompt as a paragraph (`course_kit_export.py:1072`); the PPTX path
ignores it entirely.

We are paying Gemini to design flowcharts and then printing the description of the flowchart.
This is the single largest quality gap, and closing it requires **no new vendor, no new
dependency, and no AI change** — only a renderer.

### 1.2 Layout is guessed, not measured

```python
def _wrapped_lines(text, width_in, sz):
    chars_per_line = max(10, int(width_in * 96 / (sz * 0.55)))
    return max(1, -(-len(text) // chars_per_line))
```

`0.55` is an average character width. Every stacked block on every slide is spaced using this
estimate, because PowerPoint text boxes do not clip overflow — they render straight through
whatever is beneath them. Long words, digits and any non-Latin script break the estimate, and
the failure mode is silently overlapping text in a deck a lecturer is standing in front of.
The `if oy > Inches(6.5): break` guards throughout are the same problem seen from the other
side: content is *dropped* to protect the layout.

This is not fixable by prettier colours. It is fixable by measuring text (PIL/fontTools) or by
letting a real layout engine do it.

### 1.3 The renderers hardcode layout *and* content selection

`_render_common_mistakes` decides what is a mistake and what is a correction by *positional
convention* — `bullets[::2]` vs `bullets[1::2]`, falling back through `key_concepts`, then
`definitions`. The AI is not asked for mistake/correction pairs; the renderer guesses at them
from a flat list. Same in `_render_quiz`: `bullets[0]` is the question, the rest are options,
and `definitions[0]` is the answer.

So the "structured content" the brief asks for in requirement 3 is *half* built: the fields
exist, but they are generic buckets (`bullets`, `key_concepts`, `definitions`) that each
renderer reinterprets. The structure the AI emits does not match the structure the renderer
needs.

### 1.4 The worker image has no browser and no Node

`backend/Dockerfile` is `python:3.12-slim`. No Chromium, no LibreOffice, no Node. Every
HTML-based option below implies adding one of those to the heavy-worker image (+400MB, a new
CVE surface, and a dev-parity problem on Windows `--pool=solo`).

---

## 2. Tool survey

Researched July 2026. Status verified against vendor docs, not memory — this market moves.

| Tool | Licence | API? | Output | Editable PPTX? | Verdict for VIDYA |
|---|---|---|---|---|---|
| **Gamma.app** | Commercial | **Yes** — v1.0 GA Nov 2025, Pro/Ultra/Teams/Business plan + credits | pptx, pdf, web | Yes | **Viable, later.** Best-in-class output. Sends syllabus content to a third party; credit cost per deck; themes must be pre-created in Gamma and referenced by ID |
| **Tome** | — | — | — | — | **Dead.** Presentation product shut down 30 Apr 2025; company pivoted to sales, brand acquired by AngelList. Remove from consideration |
| **Beautiful.ai** | Commercial | Early access only, no public GA | Editable deck | Yes | Not evaluable — cannot design against an unpublished contract |
| **Canva** | Commercial | Connect API — **Enterprise org required** | Canva design | Via export | **No.** Autofill only fills *text and image* fields in a pre-made brand template. Cannot vary layout per slide, which is the entire requirement |
| **Marp** | MIT | CLI (Node + Chromium) | pdf, pptx, html | **No** — pptx is pre-rendered bitmaps per slide | Export-only. `--pptx-editable` exists but is experimental, needs LibreOffice *and* Chromium, and the Marp team explicitly does not recommend it when appearance matters |
| **Reveal.js** | MIT | Library (browser) | html, pdf (via decktape) | No | Good for an in-app *web* deck. Not a PPTX path |
| **PptxGenJS** | MIT | Library (**Node**) | pptx | **Yes** | Real editable PPTX, nicer API than python-pptx — but it is JavaScript. Costs a Node sidecar in a Python worker |
| **DeckDeckGo** | MIT (Apache-2.0 components) | Library/editor | html, pdf | No | Largely dormant; no advantage over Reveal.js |
| **Office.js** | — | Add-in runtime | — | n/a | **Category error.** Office.js runs *inside* a user's PowerPoint session; it cannot generate a file server-side in a Celery worker |

### 2.1 The finding that decides the architecture

**Every route to a beautiful deck via HTML produces an un-editable deck.**

Marp, Reveal.js and DeckDeckGo all render HTML/CSS. Getting that into PPTX means screenshotting
each slide into a bitmap — Marp says so plainly: *"PPTX converted in Marp has consisted by
pre-rendered slide images… not suitable to handle text content / re-edit the content."*

Faculty edit generated decks. A deck of JPEGs is a deck they cannot fix a typo in, cannot
reflow for their own template, and cannot make accessible (no text layer = no screen reader, no
search, no copy-paste for students). For a university publishing to students, an image-only
deck is arguably an accessibility regression, not an upgrade.

So the choice is not "python-pptx vs. something prettier". It is:

- **Native shapes** (python-pptx / PptxGenJS) → editable, accessible, and *we* own the layout quality.
- **HTML render** (Marp / Reveal) → prettier per pixel, but flat images, or a web-only artifact.
- **Gamma** → both editable and beautiful, because they solved this problem themselves — at the cost of sending tenant content off-platform per deck.

**Recommendation: invest in the native-shape path, keep HTML as a web-preview side channel, and
leave a Gamma-shaped hole in the architecture for when the governance question is answered.**

---

## 3. Image and icon licensing

| Source | Licence | Verdict |
|---|---|---|
| **Lucide** | ISC | **Use this.** Permissive, no runtime attribution, vendor the SVGs. Already the frontend's icon set — same visual language in the app and the deck |
| **Heroicons** | MIT | Fine as a supplement; keep to one family for visual consistency |
| **Icons8** | Proprietary | **Avoid on free tier.** Requires a link back to icons8.com "wherever you use them" — that means an attribution link inside every exported deck. Paid tier removes it; not worth the bill |
| **Unsplash** | API Terms | **Cannot use for exports.** The API Guidelines require *hotlinking* the returned URL and triggering download events. A PPTX embeds image bytes and is opened offline — that is structurally incompatible with hotlinking, independent of the photo licence itself |
| **OpenMoji** | CC BY-SA 4.0 | **Avoid.** ShareAlike: recolouring an icon to our palette is a derivative, which the licence wants redistributed under CC BY-SA. Attribution required per deck. Not worth the legal ambiguity for emoji |

**Conclusion: Lucide only, vendored into the repo at build time.** Icons ship as SVG; python-pptx
cannot place SVG, so pre-render the ~40 we actually use to PNG at 2x, or convert paths to pptx
freeform shapes. No network calls at export time — the current logo fetch already does a live
`urllib.request.urlopen(logo_url, timeout=5)` inside the render path (`course_kit_export.py:398`),
which is a worker stall waiting to happen and should be cached regardless.

Photographs: skip entirely for v1. Stock photos on lecture slides are decoration, and every
compliant source costs either attribution surface or money. Icons and diagrams carry meaning;
photos mostly do not.

---

## 4. Proposed architecture

The brief asks for a generator hierarchy. The generators are the easy part — **the leverage is
in the contract between them**, otherwise each new backend re-derives "what is a mistake vs. a
correction" the way `_render_common_mistakes` does today.

### 4.1 Three layers, one intermediate representation

```
  AI (Gemini)                  Planner                     Renderer
 ─────────────           ──────────────────          ────────────────────
  structured      →      SlideSpec (IR)        →      PresentationGenerator
  JSON per slide         validated, typed,           ├── PythonPptxGenerator   (default, editable)
                         layout-agnostic,            ├── HtmlSlideGenerator    (web preview)
                         no vendor concepts          ├── RevealJsGenerator     (in-app present mode)
                                                     └── GammaGenerator        (stub, when approved)
```

**SlideSpec is the whole design.** A typed, versioned, vendor-neutral description of *what is
on the slide and what it means* — never how many inches from the left. Sketch:

```python
class SlideSpec(BaseModel):
    slide_number: int
    title: str
    layout: LayoutHint          # TITLE | SPLIT | FULL_BLEED | COMPARISON | TIMELINE | DIAGRAM | CODE
    blocks: list[Block]         # discriminated union
    notes: SpeakerNotes | None
    meta: SlideMeta             # bloom, co_reference, unit — provenance, printed in the footer

# Block = BulletList | Comparison | Timeline | Diagram | CodeBlock | Callout | Definition | Quiz
class Comparison(BaseModel):
    kind: Literal["comparison"]
    left_heading: str
    right_heading: str
    rows: list[ComparisonRow]   # {left, right} — PAIRED at the source, not bullets[::2]

class Diagram(BaseModel):
    kind: Literal["diagram"]
    diagram_type: Literal["flowchart", "block", "sequence", "cycle", "hierarchy"]
    nodes: list[DiagramNode]    # {id, label, icon: LucideIcon | None}
    edges: list[DiagramEdge]    # {from, to, label}
```

Three properties make this worth the effort:

1. **The AI emits the structure the renderer needs.** `Comparison.rows` is paired by the model,
   which knows which correction goes with which mistake. `bullets[::2]` disappears.
2. **A diagram becomes data, not prose.** `nodes`/`edges` render as *native pptx connectors and
   shapes* — editable, on-brand, no Chromium. `diagram_prompt` (free text) is unrenderable by
   construction; a node/edge graph is trivially renderable.
3. **Every generator consumes the same IR.** Adding Gamma later means writing a SlideSpec →
   Gamma-markdown adapter, not touching the AI layer or M03's service. That is requirement 5,
   satisfied structurally rather than by intention.

### 4.2 The generator contract

```python
class PresentationGenerator(Protocol):
    format: ClassVar[str]              # "pptx" | "html" | "reveal"
    editable: ClassVar[bool]           # does the output have a text layer?
    requires_network: ClassVar[bool]   # governance gate — see §6

    def supports(self, spec: DeckSpec) -> Capability: ...   # FULL | DEGRADED | UNSUPPORTED
    def render(self, spec: DeckSpec, theme: Theme) -> bytes: ...
```

`supports()` is the honest part. A generator that cannot draw a sequence diagram should say
`DEGRADED` and let the caller decide, rather than silently emitting bullets — which is exactly
today's failure. Selection stays in the existing `export_format` dispatch in `_run_export`; no
router or API change.

`Theme` carries the palette, type scale and spacing rules as *data* (tenant `primary_color`
already flows in). Today `_NAV`/`_ACC`/`_TEAL` are locals inside a 700-line function and the
type scale is `sz=` literals at ~40 call sites.

### 4.3 Layout engine, briefly

Native-shape rendering needs real text measurement to kill `_wrapped_lines`. `PIL.ImageFont`
+ the actual TTF gives exact pixel metrics; measure → wrap → stack → place. Slides then *fit*
instead of being estimated at, and content stops being dropped by `break` guards. This is
unglamorous and is probably the highest-value item in the whole document after the diagram
renderer.

---

## 5. Recommended implementation (phased)

| Phase | Scope | Why this order |
|---|---|---|
| **0** ✅ | `DIAGRAM` renderer for native pptx shapes + structured `Diagram` block in the AI schema | Highest value per unit of work. The AI already generates the content; we are discarding it |
| **1** ✅ | Extract `Theme` + text measurement; delete `_wrapped_lines` | Fixes overlap and dropped content — correctness, not polish |
| **2** | Introduce `SlideSpec` IR + `PresentationGenerator` protocol; port existing renderers behind it | The refactor the brief asks for. Do it *after* 0–1 so the IR is designed against renderers we have actually fixed |
| **3** | Lucide icons vendored + `Callout`/`Comparison`/`Timeline` blocks | The visual-hierarchy asks. Cheap once the IR exists |
| **4** | `HtmlSlideGenerator` (Jinja + CSS) for in-app preview | Students/faculty see the deck without downloading. No new worker deps — render in the browser |
| **5** | `GammaGenerator` stub behind a tenant flag | Only when §6 is answered |

python-pptx is **not removed** at any phase, per requirement 1. It stays the default and only
editable path.

### 5.1 Libraries

| Library | Licence | Purpose | New dep? |
|---|---|---|---|
| `python-pptx>=1.0.0` | MIT | Current, stays default | No |
| `pydantic>=2` | MIT | SlideSpec validation | No |
| `Pillow` | MIT-CMU | Text metrics, icon rasterisation | **Yes** (small, pure-ish) |
| `jinja2` | BSD-3 | HTML generator (phase 4) | Likely transitive |
| Lucide SVGs | ISC | Icon set, vendored | **Yes** (assets, not a package) |
| `graphviz` / `mermaid-cli` | — | Complex auto-layout diagrams | **Deliberately not proposed** — both need a system binary or Node+Chromium in the worker image. Hand-rolled layout for 5 diagram types is cheaper than that dependency |

Nothing here requires Chromium, Node, or LibreOffice in the backend image.

---

## 6. Risks

**Gamma sends tenant content to a third party.** This is a governance decision, not a technical
one. CLAUDE.md mandates tenant isolation and that all AI output is logged to AuditLog with model,
prompt_hash and confidence. A Gamma generation is an AI output produced by a model we cannot
name, with a prompt we do not hash, on a server we do not control. Before any Gamma work:
Srinivas signs off, and we answer where the syllabus text is stored and for how long. **Do not
prototype this against a real tenant's syllabus.**

**Gamma's theme constraint is real.** *"Themes must be pre-created in Gamma and referenced by ID."*
Per-tenant branding therefore means manually creating a Gamma theme per tenant — which does not
scale with a multi-tenant SaaS and quietly breaks the white-label story.

**Credit cost is per-deck and uncapped.** Gamma bills 1–3 credits per card plus 2–125 per image.
A 20-slide kit regenerated a few times per unit per semester across every course is a real line
item and needs a modelled ceiling before anyone commits.

**The IR refactor touches a 1450-line worker with no test coverage I could find.** Sequencing
phases 0–1 first means each lands independently and is verifiable by opening the file.

**Effort is dominated by design, not code.** Making a flowchart *look good* at arbitrary node
counts is genuinely hard; the first version will handle 3–7 nodes in one direction and should
say `DEGRADED` above that rather than emit spaghetti.

**Marp/Reveal remain a trap.** If someone later asks "why not just use Marp, it looks better" —
§2.1. Image-only decks are an accessibility and editability regression.

---

## 7. Effort estimate

Rough, and the diagram work is the uncertain one.

| Phase | Estimate | Confidence |
|---|---|---|
| 0 — Diagram renderer + AI schema | 3–5 days | Medium — layout quality is the risk |
| 1 — Theme + text measurement | 2–3 days | High |
| 2 — SlideSpec IR + protocol + port | 5–8 days | Medium — touches every renderer |
| 3 — Icons + new block types | 3–4 days | High |
| 4 — HTML generator | 3–4 days | High |
| 5 — Gamma stub | 2 days + governance | Low — blocked on §6 |
| **Total (0–4, no vendor)** | **~3 weeks** | — |

Phases 0 and 1 alone (~1 week) close most of the visible gap, because the decks are not ugly for
lack of a vendor — they are ugly because we render designed diagrams as bullet points and guess
at text wrapping.

---

## Sources

- [Gamma Developer Docs](https://developers.gamma.app/) · [API availability & plans](https://help.gamma.app/en/articles/11962420-does-gamma-have-an-api) · [Access and pricing](https://developers.gamma.app/get-started/access-and-pricing.md)
- [Why Tome pivoted away from presentations](https://autoppt.com/blog/tome-app-pivot-away-from-presentations/) · [Tome shutdown timeline](https://deckary.com/blog/tome-review)
- [Beautiful.ai API (early access)](https://support.beautiful.ai/hc/en-us/articles/43654071102605-Beautiful-ai-API)
- [Canva Connect — Autofill guide](https://www.canva.dev/docs/connect/autofill-guide/) · [Brand templates API](https://www.canva.dev/docs/connect/api-reference/brand-templates/)
- [Marp — exported PPTX cannot be re-edited](https://github.com/orgs/marp-team/discussions/82) · [marp-cli](https://github.com/marp-team/marp-cli)
- [Lucide licence (ISC)](https://lucide.dev/license) · [Heroicons licence](https://www.licenseorg.com/guide/design-graphics/heroicons)
- [Icons8 licence](https://icons8.com/license)
- [Unsplash API Guidelines](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines) · [Unsplash API Terms](https://unsplash.com/api-terms)
- [OpenMoji FAQ / licence](https://openmoji.org/faq/) · [OpenMoji CC BY-SA discussion](https://github.com/hfg-gmuend/openmoji/issues/505)
