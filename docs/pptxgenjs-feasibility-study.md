# PptxGenJS vs python-pptx — Architectural Feasibility Study

**Status:** Feasibility review. Nothing implemented, nothing committed.
**Module:** M03 Course Kit · `backend/app/workers/heavy/course_kit_export.py`
**Companion:** `docs/course-kit-presentation-architecture.md` (phases 0-1 implemented)
**Date:** 2026-07-17

---

## 0. Recommendation first

**No. VIDYA should not migrate from python-pptx to PptxGenJS.**

Your five constraints — offline, no API cost, no data egress, editable PPTX, multi-tenant — are all
*already satisfied by python-pptx*. They are arguments against Gamma, and they are correct
arguments against Gamma. But they do not discriminate between two offline OOXML writers: PptxGenJS
satisfies exactly the same five, and so does the library we already use. The constraints rule out
the vendor; they do not select the replacement.

Three findings decide it, in order of weight:

1. **PptxGenJS would regress the diagram feature we shipped last week.** It has no anchored
   connectors — [issue #399](https://github.com/gitbrent/PptxGenJS/issues/399) has been open since
   September 2018, and the TypeScript definitions contain no `stCxn`/`endCxn`/`connect`/`anchor`
   property of any kind. Its lines are absolute x/y/w/h with an arrowhead. Our phase-0 flowcharts
   use python-pptx's `begin_connect()`/`end_connect()`, which emit real `<p:cxnSp>` connectors
   (verified in the rendered XML). In PowerPoint that is the difference between dragging a box and
   having the arrow follow it, versus dragging a box and leaving the arrow behind. **"PPT must
   remain fully editable" is your requirement, and PptxGenJS is the option that weakens it.**

2. **Neither library does layout, so switching buys no visual improvement.** This is the crux. Both
   are OOXML serialisers: you give both of them a rectangle at 3.2 inches from the left, and both
   write the same XML. The deck was never ugly because of python-pptx. Phases 0-1 are the proof —
   we made the decks materially better (diagrams that draw, text that stops overlapping) with *zero*
   library change, because the gap was our renderer. Migrating rewrites ~1,450 lines of layout code
   into a second language to produce byte-equivalent output.

3. **python-pptx has a raw-XML escape hatch; PptxGenJS does not.** `shape._element` exposes lxml, so
   anything the library lacks, we inject — we already do this for arrowheads (`<a:tailEnd>`), which
   python-pptx has no API for either. PptxGenJS builds its XML internally with no documented
   extension point. With python-pptx, a missing feature costs an afternoon. With PptxGenJS, it costs
   a fork.

The honest counter-case is in §1.3 and it is not nothing: PptxGenJS can *create slide masters*, and
python-pptx cannot. That is a real capability gap and it points at a real defect in our decks. §6
shows how to close it in python-pptx for a fraction of a migration — using a mechanism PptxGenJS
structurally cannot use, because it cannot read a `.pptx` at all.

---

## 1. Comparison for VIDYA specifically

Verified against vendor docs and type definitions July 2026, not from memory. "Same" means both
emit the same OOXML and the difference is API ergonomics only.

| Capability | python-pptx | PptxGenJS | Why it matters here |
|---|---|---|---|
| **Layout flexibility** | Absolute EMU positioning | Absolute inch/pct positioning | **Same.** Neither has a layout engine. Both require us to compute every coordinate — which is the actual work |
| **Typography** | Set font/size/colour per run; no metrics | Same; no metrics | **Same.** Neither measures text. We ship Carlito to measure (phase 1); in Node this becomes opentype.js — the same work, ported |
| **Theme support** | Colours/fonts per run; theme via template | Colours/fonts per run; `defineSlideMaster()` | **PptxGenJS wins** — see §1.3 |
| **Icons** | No SVG; pre-render to PNG | **SVG via `addImage`** — modern PowerPoint / M365 only | PptxGenJS wins, mildly. SVG silently fails on older Office, so a university on Office 2016 gets nothing; we would ship PNG fallbacks anyway |
| **SVG support** | None natively | Yes, with the caveat above | Same conclusion |
| **Tables** | Full, incl. cell merge | Full, incl. `colspan`/`rowspan` | **Same** |
| **Charts** | `add_chart` + `CategoryChartData` | `addChart`: area, bar, bar3D, bubble, doughnut, line, pie, radar, scatter | **Same** (both native, editable charts). PptxGenJS's API is nicer. M03 currently renders zero charts |
| **Diagrams / flowcharts** | **Anchored connectors** (`<p:cxnSp>`) | **Static lines only** — #399 open since 2018 | **python-pptx wins decisively.** This is the feature we just shipped |
| **Timelines** | Build from shapes | Build from shapes | **Same.** Neither has a timeline primitive; it's our layout code either way |
| **Smart layouts** | None (no SmartArt) | None (no SmartArt) | **Same.** Neither writes SmartArt. Any "smart" layout is code we write |
| **Images** | png/jpg/gif, base64 or path | png/jpg/gif/svg, base64 or path | Near-same |
| **Animations** | **None** | **None** | **Same.** Neither library writes animations or transitions. If animation is ever a requirement, *neither* option delivers it |
| **Maintainability** | Python — same language, tests, CI, reviewers as the rest of M03 | JavaScript — a second toolchain inside a Python worker | **python-pptx wins.** See §1.4 |
| **Performance** | In-process, no IPC | Node subprocess or sidecar per export: process start + JSON serialisation of the whole kit | **python-pptx wins.** Not fatal, but pure added cost |
| **Editable PPT quality** | Real connectors; free-floating shapes today | SVG icons; real masters; no connectors | **Split** — §1.3 |
| **Reads existing .pptx** | **Yes** | **No** — "not designed to import existing presentations and/or templates" | **python-pptx wins.** This is what makes §6 possible |
| **Raw XML escape hatch** | `shape._element` (lxml) | None | **python-pptx wins.** Our arrowheads already depend on this |
| **Maintenance** | Active, 1.0 stable | v4.0.1, last publish ~1 year ago | Slight edge python-pptx; neither is abandoned |

### 1.3 The honest case for PptxGenJS: masters

`defineSlideMaster()` creates **real slide masters and layouts with placeholders** (`title`, `body`,
`pic`, `chart`, `tbl`, `media`) which become first-class Layouts in the exported file, editable
under View > Slide Master. python-pptx **cannot create a layout or master at all** — its docs are
explicit that you use the layouts already present in the file you opened.

This points at a genuine defect in our decks, and it is worth stating plainly. Today
`_generate_pptx` does:

```python
BLANK = prs.slide_layouts[6]
...
def _clear_placeholders(slide):
    for ph in list(slide.placeholders):
        sp = ph._element
        sp.getparent().remove(sp)
```

Every slide is the **blank** layout with **every placeholder deleted**, covered in free-floating
text boxes. That is why the decks feel un-native: a faculty member cannot re-theme them, PowerPoint's
outline view is empty, "Reset Slide" does nothing, and accessibility tools see anonymous boxes rather
than a title. **This is the strongest argument in the brief, and it is an argument about
placeholders, not about PptxGenJS.**

The catch: python-pptx cannot *create* masters, but it can *use* them — and PptxGenJS can do
neither, because it cannot open a `.pptx`. python-pptx's own documented recipe is exactly the fix:
build a deck with the styles, logo and layouts you want, delete its slides, and load it as your
starting point. §6 develops this. It is better than `defineSlideMaster()` for our case, because a
designer builds the master *in PowerPoint* where they can see it, instead of a developer describing
it in JSON.

### 1.4 Maintainability, concretely

The migration is not "python-pptx → PptxGenJS". It is "one Python worker" → "a Python worker that
serialises a kit to JSON, spawns or calls Node, handles its failure modes, and streams bytes back",
plus a Node image, a second dependency tree, a second security-patch surface, and JS reviewers on a
Python team. `backend/Dockerfile` is `python:3.12-slim` with no Node. And M03's heavy worker already
runs `--pool=solo` on Windows for dev parity — a subprocess boundary is one more thing to get wrong
there.

---

## 2. Can PptxGenJS completely replace python-pptx?

**No.** Functionality python-pptx provides that PptxGenJS cannot:

1. **Anchored connectors.** No `stCxn`/`endCxn` equivalent exists in the API. Our flowchart, cycle
   and hierarchy diagrams would degrade to static lines that detach on edit.
2. **Reading/modifying an existing `.pptx`.** Explicitly out of scope for the library. This kills
   template-based tenant branding (§6) and any future "import the university's deck" feature.
3. **Raw XML access.** No documented extension point. Everything the API lacks is unreachable — we
   would already be blocked on arrowheads, which we implement by injecting `<a:tailEnd>`.
4. **In-process execution from Python.** Not a library feature, but a hard architectural fact: every
   export gains a process boundary.

Conversely, PptxGenJS provides two things python-pptx cannot:

1. **Programmatic slide masters/layouts with placeholders** (workaround: ship a template `.pptx` —
   §6, and strictly better for us).
2. **Native SVG images** (workaround: pre-render Lucide to PNG at 2×, which we need anyway for
   Office 2016 compatibility).

Both python-pptx gaps have workarounds we would want regardless. Neither PptxGenJS gap does.

---

## 3. Migration analysis (if it were pursued anyway)

**Files affected**

| Area | Detail |
|---|---|
| `backend/app/workers/heavy/course_kit_export.py` | ~1,450 lines. The PPTX half (~800) rewritten in TS; the PDF/handout half (reportlab) stays Python and now diverges from it |
| `backend/app/modules/m03_course_kit/presentation/` | All of phases 0-1 ported: `theme.py`, `text_metrics.py`, `diagram.py` |
| Text metrics | Carlito + Pillow → opentype.js. The *equivalence trick* survives (Carlito is metric-identical to Calibri — verified) but the measurement code is rewritten |
| Diagram renderer | Rewritten **and degraded** — no connectors |
| `backend/Dockerfile` | Node runtime added to a Python image |
| New service | Node renderer: JSON contract, error mapping, timeouts, health, logging, S3 or byte-return path |
| Also affected | `m08_exam_setter/pdf_exporter.py` and other exporters remain Python — the export story is now bilingual |

**Complexity: high.** Not algorithmically, but it is a cross-language rewrite of the most
layout-dense code in the codebase, with no test coverage to catch regressions, for identical output.

**Risks**
- Silent visual regressions: no golden-file tests exist; the current safety net is opening the file.
- Diagram regression is not a risk but a **certainty** (§2.1).
- Two runtimes in one worker; Windows `--pool=solo` dev parity.
- Node CVE surface in a container that today has none.
- Bus factor: JS renderer in a Python team.

**Backward compatibility.** Existing `KitSlide.content` JSONB is engine-agnostic, so stored kits
survive. `DiagramSpec` (phase 0) also survives — it is our schema, not python-pptx's. Nothing in the
DB blocks this; the cost is entirely in the renderer.

**Export compatibility.** Both write OOXML that PowerPoint, Google Slides and LibreOffice open.
Filenames, S3 keys, `StorageAsset` rows and the `COURSE_KIT_EXPORT_COMPLETED` audit event are
unaffected. **Except**: PptxGenJS decks would open with detached arrows on any deck a faculty member
edits — a compatibility loss invisible at export time and visible in the lecture hall.

---

## 4. Architecture — the part worth building regardless

The brief's real requirement is *"the rest of VIDYA AI should never know which engine is being
used."* **That is delivered by the protocol and the IR, not by the choice of library** — and it is
already scoped as phase 2 of the companion doc. Build it, and the PptxGenJS question becomes cheap
to answer later with a prototype instead of a rewrite.

```
  AI (Gemini)              Planner                    Renderer
 ─────────────       ──────────────────         ────────────────────────
  structured    →    SlideSpec (IR)       →     PresentationGenerator
  JSON               validated, typed,          ├── PythonPptxGenerator   (default, editable)
                     layout-agnostic,           ├── HtmlSlideGenerator    (in-app preview)
                     vendor-neutral             └── PptxGenJsGenerator    (only if §0 is overturned)
```

```python
class PresentationGenerator(Protocol):
    format: ClassVar[str]              # "pptx" | "html"
    editable: ClassVar[bool]
    supports_connectors: ClassVar[bool]  # PptxGenJS would declare False — and it would be visible

    def supports(self, spec: DeckSpec) -> Capability: ...   # FULL | DEGRADED | UNSUPPORTED
    def render(self, spec: DeckSpec, theme: Theme) -> bytes: ...
```

`supports_connectors` is the point: a generator must **declare** what it degrades, rather than
quietly shipping a worse deck. Our phase-0 `capability()` already works this way, returning
`DEGRADED` rather than drawing spaghetti. The protocol is where "VIDYA never knows the engine" gets
enforced — the service layer keeps calling `export_course_kit(format="pptx")` and never names a
library.

---

## 5. Diagram rendering — what each engine can do

We have already implemented four of these natively (phase 0, `presentation/diagram.py`).

| Diagram | Status | python-pptx | PptxGenJS |
|---|---|---|---|
| **Flowchart** | ✅ shipped | Rounded rects + anchored connectors; straight/elbow routing | Static lines — detach on edit |
| **Process** | ✅ shipped | Same as flowchart (`_layout_row` / `_layout_column`) | As above |
| **Cycle** | ✅ shipped | Elliptical placement + elbow return edges | As above |
| **Hierarchy / Org chart** | ✅ shipped | BFS depth layout, one row per level | As above |
| **Architecture / block** | ✅ shipped | `_layout_grid` | As above |
| **Timeline** | Not built | Shapes + a rule; ~1 day | Same effort |
| **Comparison table** | Partial | Native pptx table; needs paired `Comparison` block from AI (today `bullets[::2]`) | Native table; same |
| **Mind map** | Not built | Radial layout is genuinely hard to make look good; recommend **DEGRADED → hierarchy** | Same, minus connectors |
| **SVG diagrams** | N/A | Not natively — and a rasterised diagram is *not editable*, which defeats the purpose | Supported, same objection |

On SVG diagrams specifically: rendering a diagram *as an SVG image* would make it prettier and
uneditable in one move — the same trap as Marp in the companion doc (§2.1 there). Native shapes are
the whole point. SVG's legitimate use here is **icons**, which are decorative and never edited.

---

## 6. Theme system — the actual upgrade

This is where the effort in this brief should go, and it does not require a new library.

**The fix is a template `.pptx` per theme.** A designer builds masters and layouts in PowerPoint —
title, section, content, two-column, diagram, quiz — with real placeholders and the brand applied.
We `Presentation("theme.pptx")`, delete the sample slides, and `add_slide(layout)` per slide,
**filling placeholders instead of deleting them**. Decks stop being anonymous boxes: outline view
works, Reset Slide works, screen readers find titles, and a faculty member can re-theme with one
click.

This is python-pptx's own documented recipe, and **it is unavailable to PptxGenJS at any price**,
because it cannot open a `.pptx`.

```python
@dataclass(frozen=True)
class Theme:
    palette: Palette          # implemented (phase 1)
    type: TypeScale           # implemented (phase 1)
    template: Path | None     # NEW — the .pptx carrying masters + layouts
    layouts: dict[str, int]   # NEW — semantic name -> layout index ("diagram" -> 4)
    mode: Literal["light", "dark"]
```

- **University branding.** `Theme.for_tenant()` exists and overrides the accent only — deliberately,
  since green means *summary* and red means *mistake*; a university whose brand is red must not turn
  every correct answer red. Extend to select a per-tenant template + logo. Store templates as
  tenant-scoped S3 assets, resolved at export.
- **Faculty branding.** Technically identical to tenant branding. But flag it as a **governance
  question, not a technical one**: a course kit is an institutional teaching artifact, and per-faculty
  visual identity on it is a policy decision for Srinivas. Recommend faculty *name* attribution
  (already on the cover) and **not** faculty palettes.
- **Dark/light.** Cheap in the palette (`Theme.mode` selecting two `Palette` instances), but note it
  is a *projector* decision, not a taste one: dark decks wash out on low-contrast projectors, which is
  what most lecture halls have. Ship light as default, dark as opt-in.
- **Master slide layouts.** As above — the core of this section.
- **Palette / typography.** Already data (phase 1).

---

## 7. AI output — structured slide specifications

Also engine-independent, and **already half-built**: phase 0 landed `DiagramSpec` (nodes/edges),
replacing the `diagram_prompt` prose that the renderer could not draw. The remaining fields follow
the same principle — *the AI emits the structure the renderer needs, rather than generic buckets each
renderer reinterprets.*

```python
class SlideSpec(BaseModel):
    slide_number: int
    title: str
    layout: LayoutHint              # TITLE | SPLIT | COMPARISON | TIMELINE | DIAGRAM | CODE | QUIZ
    objectives: list[str]
    blocks: list[Block]             # discriminated union
    key_points: list[str]
    summary: str | None
    icons: list[IconHint]           # Lucide names — from a VALIDATED enum, not free text
    images: list[ImageHint]         # advisory only; see below
    notes: SpeakerNotes | None
    meta: SlideMeta                 # bloom, co_reference — provenance for the footer

# Block = BulletTree | Comparison | Timeline | Diagram | Table | CodeBlock | Callout | Quiz
class BulletTree(BaseModel):        # hierarchy, not a flat list
    kind: Literal["bullets"]
    items: list[BulletNode]         # {text, children: list[BulletNode], emphasis: bool}

class Comparison(BaseModel):
    kind: Literal["comparison"]
    left_heading: str
    right_heading: str
    rows: list[ComparisonRow]       # {left, right} — PAIRED BY THE MODEL

class Timeline(BaseModel):
    kind: Literal["timeline"]
    events: list[TimelineEvent]     # {label, caption, marker}

class Table(BaseModel):
    kind: Literal["table"]
    headers: list[str]
    rows: list[list[str]]           # validated rectangular — a ragged table is a render crash
```

Three notes that matter more than the field list:

- **`Comparison.rows` kills `bullets[::2]`.** `_render_common_mistakes` currently pairs mistakes with
  corrections *by position in a flat list*, guessing at structure the model was never asked for. The
  model knows which correction belongs to which mistake; ask it.
- **`icons` must be a validated enum, not free text.** A hallucinated `"lucide:brain-circuit"` that
  doesn't exist is a missing icon at render time. Validate against the vendored set at the AI
  boundary and drop unknowns — exactly as phase 0 drops undrawable diagrams via `capability()`.
- **`images` should stay advisory and unused for now.** Per the companion doc, every compliant photo
  source costs attribution surface or money, and **Unsplash's API is structurally unusable for
  exports** because it mandates hotlinking while a PPTX embeds bytes and opens offline. Let the AI
  suggest; let a human choose.

---

## 8. Answer

**Should VIDYA AI migrate from python-pptx to PptxGenJS? No.**

It would cost a cross-language rewrite of the most layout-dense code we own, add a Node runtime to a
Python worker, and **regress the diagram feature we shipped last week**, in exchange for byte-equivalent
output — because both libraries are OOXML serialisers and neither one lays anything out. The two things
PptxGenJS genuinely does better (masters, SVG icons) both have workarounds in python-pptx that we want
anyway, while the things python-pptx does better (anchored connectors, template ingestion, raw XML)
have no workaround in PptxGenJS at all.

**Expected visual improvement from migrating: none.** That is the finding to take away. Phases 0-1
demonstrated it from the other direction — the decks got materially better with no library change,
because the constraint was never the library.

### Where the effort should go instead

| Phase | Scope | Effort | Visual payoff |
|---|---|---|---|
| **2** | `SlideSpec` IR + `PresentationGenerator` protocol; port existing renderers | 5-8 days | None directly — but this is what makes the engine swappable, and answers the brief's §4 |
| **2.5** | **Template-based masters + placeholders** (§6) | 4-6 days + design time | **High.** Native, re-themeable, accessible decks. The real content of the brief's §1.3 |
| **3** | Lucide icons (PNG, vendored) + `Comparison`/`Timeline`/`Callout` blocks + paired AI output (§7) | 4-6 days | **High** |
| **4** | HTML preview generator | 3-4 days | Medium — students/faculty see decks without downloading |
| — | ~~PptxGenJS migration~~ | ~~4-6 weeks + permanent Node ops cost~~ | ~~Zero~~ |

**~3 weeks for all of 2 → 4**, versus 4-6 weeks to migrate for no visual gain and one certain
regression.

### If you want to keep the option open

Do phase 2 first. Once `PresentationGenerator` exists, a `PptxGenJsGenerator` is a contained
experiment behind a flag — one generator, one JSON contract, `supports_connectors = False` declared
honestly — rather than a migration. If PptxGenJS closes #399 (open 8 years), re-run this study
against the protocol instead of against the codebase. That is the version of "future generators"
worth paying for, and phase 2 buys it whether or not PptxGenJS ever wins.

---

## Sources

- [PptxGenJS issue #399 — anchor connection feature (open since Sept 2018)](https://github.com/gitbrent/PptxGenJS/issues/399) · [types/index.d.ts](https://github.com/gitbrent/PptxGenJS/blob/master/types/index.d.ts) · [Shapes API](https://gitbrent.github.io/PptxGenJS/docs/api-shapes/) · [Masters and Placeholders](https://gitbrent.github.io/PptxGenJS/docs/masters.html) · [Images API](https://gitbrent.github.io/PptxGenJS/docs/api-images/) · [Charts API](https://gitbrent.github.io/PptxGenJS/docs/api-charts/) · [npm](https://www.npmjs.com/package/pptxgenjs)
- [python-pptx — Working with Slides / templates](https://python-pptx.readthedocs.io/en/latest/user/slides.html) · [Concepts](https://python-pptx.readthedocs.io/en/latest/user/concepts.html) · [Connector shape](https://python-pptx.readthedocs.io/en/latest/dev/analysis/shp-connector.html)
