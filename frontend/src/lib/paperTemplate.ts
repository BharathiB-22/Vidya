// M08 Exam Setter — Paper Template: the source of truth for a paper's structure.
//
//     PaperTemplate ──compileSpecs()──▶ QuestionSpec[] ──▶ AI writes content
//                                            │                    │
//                                            └──────▶ Editor ◀────┘
//                                                        │
//                                                        ▼
//                                                       PDF
//
// This file mirrors backend/app/modules/m08_exam_setter/paper_template.py. The two
// MUST stay in step: the builder previews a paper here, the worker generates it
// there, and both the editor and the PDF rebuild it from the same document. Any
// divergence shows up as a paper that previews differently from how it prints.
//
// The model is what a faculty member already has in their head:
//
//     Paper
//       └── Section              a logical grouping. HAS NO UNIT.
//             ├── name           free text — "A", "Part A", "Module 1", anything
//             ├── instruction    printed verbatim
//             ├── answer_rule    ALL | ANY_K(k)   — counts printed questions
//             └── QuestionDefinition[]
//                   ├── count       how many questions to write
//                   ├── marks       each
//                   ├── units       which units they come from (a pool)
//                   ├── unit_mode   DISTRIBUTE | INTEGRATE
//                   ├── type        AUTO | MCQ | SHORT | LONG | PROBLEM | ...
//                   ├── bloom       null = inherit the paper's distribution
//                   ├── difficulty  null = inherit
//                   ├── co          AUTO | specific COs
//                   ├── or_choice   print two alternatives, answer one
//                   └── parts[]     optional sub-parts a) b) c)
//
// Nothing here names a university, and there are no template "types". Every
// pattern is expressed by choosing sections, rules and definitions:
//
//     "answer any FIVE of EIGHT"  → one section, ANY_K(5), one definition count=8
//     "10 x 2 marks, all units"   → one section, ALL, one definition count=10
//     "Q1 OR Q2, one per module"  → one section per module, ANY_K(1), two definitions
//     "Q1 a) b) c)"               → a definition with parts
//
// Faculty never write per-unit rows and never place individual questions. They say
// "8 questions, 6 marks, these units" and THE COMPILER decides the distribution.
import type { BloomLevel, Difficulty, ExamQuestion } from '@/types/exam'

export type { BloomLevel, Difficulty }

export const TEMPLATE_VERSION = 3

// ── Vocabulary ──────────────────────────────────────────────────────────────

/** Answer rules — the whole choice system. */
export type AnswerMode = 'ALL' | 'ANY_K'

/** Unit pool semantics. */
export type UnitMode = 'DISTRIBUTE' | 'INTEGRATE'

/** What a definition asks the AI to write. AUTO lets marks decide. */
export type QuestionKind =
  | 'AUTO' | 'MCQ' | 'SHORT' | 'LONG' | 'PROBLEM' | 'CASE_STUDY' | 'PROGRAMMING'

export const QUESTION_KINDS: Array<{ value: QuestionKind; label: string }> = [
  { value: 'AUTO',        label: 'Auto' },
  { value: 'MCQ',         label: 'MCQ' },
  { value: 'SHORT',       label: 'Short Answer' },
  { value: 'LONG',        label: 'Long Answer' },
  { value: 'PROBLEM',     label: 'Problem' },
  { value: 'CASE_STUDY',  label: 'Case Study' },
  { value: 'PROGRAMMING', label: 'Programming' },
]

export const DIFFICULTIES: Difficulty[] = ['EASY', 'MEDIUM', 'HARD']

/** Bloom's levels, as stored on a question. */
export const BLOOM_LEVELS: BloomLevel[] = [
  'REMEMBER', 'UNDERSTAND', 'APPLY', 'ANALYSE', 'EVALUATE', 'CREATE',
]

export type CoMode = 'AUTO' | 'SPECIFIC'

/** The persisted question_type vocabulary (exam_questions.question_type). The
 *  builder's richer vocabulary maps onto it. Mirrors `_TYPE_TO_STORED`. */
const TYPE_TO_STORED: Record<string, string> = {
  MCQ:         'MCQ',
  SHORT:       'SHORT_ANSWER',
  LONG:        'LONG_ANSWER',
  PROBLEM:     'PROBLEM_SOLVING',
  CASE_STUDY:  'CASE_STUDY',
  PROGRAMMING: 'PROGRAMMING',
}

/** Map a definition's type onto the stored vocabulary. AUTO infers from marks —
 *  the same rule the generator has always used. Mirrors `stored_question_type`. */
export function storedQuestionType(t: string | null | undefined, marks: number): string {
  const k = (t ?? 'AUTO').toUpperCase()
  if (TYPE_TO_STORED[k]) return TYPE_TO_STORED[k]
  return marks <= 2 ? 'SHORT_ANSWER' : 'LONG_ANSWER'
}

// ── Document ────────────────────────────────────────────────────────────────

export interface AnswerRule {
  mode: AnswerMode
  /** Only meaningful for ANY_K. */
  k?: number
}

/** An optional sub-part of a full question — "Q1 a) b) c)". */
export interface QuestionPart {
  marks:      number
  or_choice:  boolean
  units:      number[]
  unit_mode?: UnitMode | null
  type?:      QuestionKind | null
  bloom?:     BloomLevel | null
  difficulty?: Difficulty | null
}

export interface QuestionDefinition {
  id:         string
  count:      number
  marks:      number
  /** A pool. Empty = every unit the paper covers. */
  units:      number[]
  unit_mode:  UnitMode
  type:       QuestionKind
  bloom:      BloomLevel | null
  difficulty: Difficulty | null
  co_mode:    CoMode
  co_ids:     string[]
  or_choice:  boolean
  parts:      QuestionPart[]
}

export interface PaperSection {
  id:          string
  name:        string
  instruction: string
  answer_rule: AnswerRule
  definitions: QuestionDefinition[]
}

export interface TemplateDocument {
  version:  number
  sections: PaperSection[]
}

// ── Factories ───────────────────────────────────────────────────────────────

let seq = 0
function newId(prefix: string): string {
  seq += 1
  return `${prefix}_${Date.now().toString(36)}_${seq}`
}

export function newDefinition(patch: Partial<QuestionDefinition> = {}): QuestionDefinition {
  return {
    id:         newId('qd'),
    count:      1,
    marks:      2,
    units:      [],
    unit_mode:  'DISTRIBUTE',
    type:       'AUTO',
    bloom:      null,
    difficulty: null,
    co_mode:    'AUTO',
    co_ids:     [],
    or_choice:  false,
    parts:      [],
    ...patch,
  }
}

export function newPart(patch: Partial<QuestionPart> = {}): QuestionPart {
  return { marks: 5, or_choice: false, units: [], unit_mode: null, ...patch }
}

export function newSection(index: number): PaperSection {
  return {
    id:          newId('sec'),
    name:        sectionLetter(index),
    instruction: '',
    answer_rule: { mode: 'ALL' },
    definitions: [newDefinition()],
  }
}

/** "A", "B", ... "Z", "AA" — a default name only; faculty may type anything. */
export function sectionLetter(index: number): string {
  let n = Math.max(0, index)
  let out = ''
  do {
    out = String.fromCharCode(65 + (n % 26)) + out
    n = Math.floor(n / 26) - 1
  } while (n >= 0)
  return out
}

/** A stable id, falling back to position for documents written before ids.
 *  Mirrors the backend's `_sid`. */
export function stableId(obj: { id?: string | null } | null | undefined, prefix: string, index: number): string {
  return String(obj?.id || `${prefix}${index}`)
}

// ── Normalisation (v1 / v2 → v3) ────────────────────────────────────────────

function blankDoc(): TemplateDocument {
  return { version: TEMPLATE_VERSION, sections: [] }
}

function coerceDefinition(raw: Record<string, unknown>): QuestionDefinition {
  return {
    id:         String(raw.id ?? newId('qd')),
    count:      Number(raw.count ?? 1),
    marks:      Number(raw.marks ?? 0),
    units:      ((raw.units ?? []) as unknown[]).map(Number).filter(n => !Number.isNaN(n)),
    unit_mode:  (String(raw.unit_mode ?? 'DISTRIBUTE').toUpperCase() as UnitMode),
    type:       (String(raw.type ?? 'AUTO').toUpperCase() as QuestionKind),
    bloom:      (raw.bloom ?? null) as BloomLevel | null,
    difficulty: (raw.difficulty ?? null) as Difficulty | null,
    co_mode:    (String(raw.co_mode ?? 'AUTO').toUpperCase() as CoMode),
    co_ids:     ((raw.co_ids ?? []) as unknown[]).map(String),
    or_choice:  Boolean(raw.or_choice),
    parts:      ((raw.parts ?? []) as Array<Record<string, unknown>>).map(p => ({
      marks:      Number(p.marks ?? 0),
      or_choice:  Boolean(p.or_choice),
      units:      ((p.units ?? []) as unknown[]).map(Number).filter(n => !Number.isNaN(n)),
      unit_mode:  (p.unit_mode ?? null) as UnitMode | null,
      type:       (p.type ?? null) as QuestionKind | null,
      bloom:      (p.bloom ?? null) as BloomLevel | null,
      difficulty: (p.difficulty ?? null) as Difficulty | null,
    })),
  }
}

function coerceSection(raw: Record<string, unknown>, index: number): PaperSection {
  const rule = (raw.answer_rule ?? { mode: 'ALL' }) as Record<string, unknown>
  return {
    id:          stableId(raw as { id?: string }, 'sec', index),
    name:        String(raw.name ?? ''),
    instruction: String(raw.instruction ?? ''),
    answer_rule: {
      mode: (String(rule.mode ?? 'ALL').toUpperCase() as AnswerMode),
      k:    rule.k == null ? undefined : Number(rule.k),
    },
    definitions: ((raw.definitions ?? []) as Array<Record<string, unknown>>).map(coerceDefinition),
  }
}

/**
 * Return a v3 document, upgrading older shapes in memory.
 *
 * v1 put one unit on each block; v2 gave every slot its own unit; both had
 * template "types" and a separate block kind per pattern. v3 has one shape:
 * sections of question definitions. The upgrades below reproduce exactly what an
 * older paper already printed — each old block becomes its own section, so
 * headers, order and totals are unchanged. Mirrors `normalise_definition`.
 */
export function normaliseDefinition(def: unknown): TemplateDocument {
  if (!def || typeof def !== 'object') return blankDoc()
  const d = def as Record<string, unknown>
  const version = Number(d.version ?? 1)

  if (version >= TEMPLATE_VERSION) {
    return {
      version,
      sections: ((d.sections ?? []) as Array<Record<string, unknown>>).map(coerceSection),
    }
  }

  const sections: PaperSection[] = []
  const blocks = (d.blocks ?? []) as Array<Record<string, unknown>>
  const groups = new Map<string, Record<string, unknown>>()
  for (const g of ((d.groups ?? []) as Array<Record<string, unknown>>)) {
    if (g.id) groups.set(String(g.id), g)
  }

  // v2 choice groups become one section per group (a group's blocks were
  // alternatives answered k-of-n, which is exactly a section's answer rule).
  const groupSections = new Map<string, PaperSection>()

  const targetSection = (block: Record<string, unknown>, index: number, defaultName: string): PaperSection => {
    const gid = block.group_id ? String(block.group_id) : null
    if (gid && groups.has(gid)) {
      if (!groupSections.has(gid)) {
        const g = groups.get(gid)!
        const sec: PaperSection = {
          id:          `sec_${gid}`,
          name:        String(g.name ?? ''),
          instruction: '',
          answer_rule: { mode: 'ANY_K', k: Number(g.answer ?? 1) },
          definitions: [],
        }
        groupSections.set(gid, sec)
        sections.push(sec)
      }
      return groupSections.get(gid)!
    }
    const sec: PaperSection = {
      id:          `sec_${stableId(block as { id?: string }, 'blk', index)}`,
      name:        defaultName,
      instruction: '',
      answer_rule: { mode: 'ALL' },
      definitions: [],
    }
    sections.push(sec)
    return sec
  }

  blocks.forEach((b, i) => {
    const bid = stableId(b as { id?: string }, 'blk', i)

    if (b.kind === 'SECTION') {
      // v2 slots each carried a unit; v1 blocks carried one unit + generate.
      const slots = b.slots as Array<Record<string, unknown>> | undefined
      let generate: number
      let units: number[]
      if (slots == null) {
        generate = Number(b.generate ?? 0)
        units = b.unit_number != null ? [Number(b.unit_number)] : []
      } else {
        generate = slots.length
        units = slots.map(s => s.unit_number).filter(u => u != null).map(Number)
      }
      const n = Math.max(0, generate)
      const answer = Number(b.answer ?? n)
      sections.push({
        id:          `sec_${bid}`,
        name:        String(b.name ?? ''),
        instruction: '',
        answer_rule: answer < n ? { mode: 'ANY_K', k: answer } : { mode: 'ALL' },
        definitions: [newDefinition({
          id: bid, count: n, marks: Number(b.marks ?? 0),
          units: [...new Set(units)].sort((x, y) => x - y),
        })],
      })
    } else if (b.kind === 'UNIT_GROUP') {
      const n = Number(b.generate ?? 0)
      const pattern = String(b.choice_pattern ?? 'COMPULSORY').toUpperCase()
      const answer = Number(b.answer ?? n)
      const unit = b.unit_number
      sections.push({
        id:          `sec_${bid}`,
        name:        `Unit ${unit}` + (b.category ? ` — ${b.category}` : ''),
        instruction: '',
        answer_rule: pattern === 'OR_CHOICE'
          ? { mode: 'ANY_K', k: 1 }
          : answer < n ? { mode: 'ANY_K', k: answer } : { mode: 'ALL' },
        definitions: [newDefinition({
          id: bid, count: n, marks: Number(b.marks ?? 0),
          units: unit != null ? [Number(unit)] : [],
        })],
      })
    } else if (b.kind === 'FULL_QUESTION') {
      const parts: QuestionPart[] = ((b.subparts ?? []) as Array<Record<string, unknown>>).map(sp => {
        const u = sp.unit_number ?? b.unit_number
        return {
          marks:     Number(sp.marks ?? 0),
          or_choice: Boolean(sp.or_choice),
          units:     u != null ? [Number(u)] : [],
        }
      })
      const sec = targetSection(b, i, String(b.label ?? ''))
      sec.definitions.push(newDefinition({ id: bid, count: 1, marks: 0, units: [], parts }))
    }
  })

  // The oldest UNIT papers had no blocks at all — they stored the compiled
  // blueprint itself ({type: "UNIT", units: [UnitBlueprint]}). Each row becomes
  // its own section, which is what those papers already printed.
  if (sections.length === 0 && Array.isArray(d.units)) {
    for (const entry of (d.units as Array<Record<string, unknown>>)) {
      const un = entry.unit_number
      const rows = (entry.rows ?? []) as Array<Record<string, unknown>>
      rows.forEach((row, ri) => {
        const n = Number(row.count ?? 0)
        if (n <= 0) return
        const pattern = String(row.choice_pattern ?? 'COMPULSORY').toUpperCase()
        const answer = Number(row.answer_count ?? n)
        const cat = String(row.category ?? '').trim()
        const rid = String(row.template_block_id ?? `u${un}r${ri}`)
        sections.push({
          id:          `sec_${rid}`,
          name:        `Unit ${un}` + (cat ? ` — ${cat}` : ''),
          instruction: '',
          answer_rule: pattern === 'OR_CHOICE'
            ? { mode: 'ANY_K', k: 1 }
            : answer < n ? { mode: 'ANY_K', k: answer } : { mode: 'ALL' },
          definitions: [newDefinition({
            id: rid, count: n, marks: Number(row.marks ?? 0),
            units: un != null ? [Number(un)] : [],
          })],
        })
      })
    }
  }

  return { version: TEMPLATE_VERSION, sections }
}

/** True when a paper's structure is owned by a template document. */
export function hasTemplate(def: unknown): boolean {
  return normaliseDefinition(def).sections.length > 0
}

// ── Unit resolution ─────────────────────────────────────────────────────────

/**
 * A definition's unit pool, resolved against the paper's own units.
 *
 * An empty pool means "every unit this paper covers". Distribution restarts per
 * definition so each one's spread reads predictably and does not depend on how
 * many questions came before it elsewhere in the paper. Mirrors backend `_Pool`.
 */
class Pool {
  units: number[]
  private i = 0

  constructor(units: number[] | null | undefined, paperUnits: number[]) {
    const chosen = (units ?? []).filter(u => u != null).map(Number)
    const allowed = (paperUnits ?? []).map(Number)
    // Only offer units the paper actually covers; fall back to the paper's own
    // units so a template built for another course still compiles.
    const pool = chosen.filter(u => !allowed.length || allowed.includes(u))
    this.units = (pool.length ? pool : allowed).length ? (pool.length ? pool : allowed) : [1]
  }

  next(): number {
    const u = this.units[this.i % this.units.length]
    this.i += 1
    return u
  }
}

// ── Spec compilation ────────────────────────────────────────────────────────

export interface QuestionSpec {
  section_id:     string
  section_name:   string
  section_order:  number
  /** The definition that owns this question — stored as template_block_id. */
  block_id:       string
  subpart_index:  number | null
  unit_numbers:   number[]
  unit_number:    number
  marks:          number
  question_type:  string
  bloom:          BloomLevel | null
  difficulty:     Difficulty | null
  co_mode:        CoMode
  co_ids:         string[]
  category:       string | null
  choice_group:   number | null
  order:          number
}

/**
 * Expand a template into one spec per question the paper must contain.
 *
 * A spec is everything the AI is told and everything the paper needs to
 * reconstruct itself. Specs come back in printed order, which is also the order
 * questions are numbered in. Mirrors backend `compile_specs`.
 */
export function compileSpecs(def: unknown, unitsIncluded: number[] = []): QuestionSpec[] {
  const doc = normaliseDefinition(def)
  const paperUnits = (unitsIncluded ?? []).map(Number)
  const specs: QuestionSpec[] = []
  // Pairs either/or alternatives for the renderer. Numbered high so it cannot
  // collide with a value a model invented.
  let orGroup = 10_000

  const add = (s: Omit<QuestionSpec, 'order'>) => specs.push({ ...s, order: specs.length })

  doc.sections.forEach((sec, si) => {
    const secId = stableId(sec, 'sec', si)
    const secName = String(sec.name ?? '')

    ;(sec.definitions ?? []).forEach((qd, di) => {
      const qdId = stableId(qd, 'qd', di)
      const count = Number(qd.count ?? 0)
      if (count <= 0) return
      const parts = qd.parts ?? []
      const pool = new Pool(qd.units, paperUnits)
      const mode = (qd.unit_mode ?? 'DISTRIBUTE').toUpperCase()

      /** [unit_numbers, primary]. INTEGRATE gives the whole pool to every
       *  question; DISTRIBUTE hands out one unit at a time. */
      const unitsFor = (): [number[], number] => {
        if (mode === 'INTEGRATE') return [[...pool.units], pool.units[0]]
        const u = pool.next()
        return [[u], u]
      }

      const base = {
        section_id:    secId,
        section_name:  secName,
        section_order: si,
        block_id:      qdId,
        co_mode:       (qd.co_mode ?? 'AUTO').toUpperCase() as CoMode,
        co_ids:        [...(qd.co_ids ?? [])],
      }

      for (let n = 0; n < count; n++) {
        if (!parts.length) {
          const marks = Number(qd.marks ?? 0)
          if (marks <= 0) continue
          const [units, primary] = unitsFor()
          let cg: number | null = null
          if (qd.or_choice) { orGroup += 1; cg = orGroup }
          for (let alt = 0; alt < (qd.or_choice ? 2 : 1); alt++) {
            add({
              ...base, subpart_index: null,
              unit_numbers: units, unit_number: primary, marks,
              question_type: storedQuestionType(qd.type, marks),
              bloom: qd.bloom ?? null, difficulty: qd.difficulty ?? null,
              category: secName || null, choice_group: cg,
            })
          }
          continue
        }

        // A full question: one spec per sub-part (two when the part is an
        // either/or), all sharing this definition's id.
        parts.forEach((part, pi) => {
          const pmarks = Number(part.marks ?? 0)
          if (pmarks <= 0) return
          let units: number[]
          let primary: number
          if (part.units?.length) {
            const ppool = new Pool(part.units, paperUnits)
            if ((part.unit_mode ?? mode).toUpperCase() === 'INTEGRATE') {
              units = [...ppool.units]
              primary = ppool.units[0]
            } else {
              const u = ppool.next()
              units = [u]
              primary = u
            }
          } else {
            [units, primary] = unitsFor()
          }
          let cg: number | null = null
          if (part.or_choice) { orGroup += 1; cg = orGroup }
          for (let alt = 0; alt < (part.or_choice ? 2 : 1); alt++) {
            add({
              ...base, subpart_index: pi,
              unit_numbers: units, unit_number: primary, marks: pmarks,
              question_type: storedQuestionType(part.type ?? qd.type, pmarks),
              bloom: (part.bloom ?? qd.bloom) ?? null,
              difficulty: (part.difficulty ?? qd.difficulty) ?? null,
              category: secName || null, choice_group: cg,
            })
          }
        })
      }
    })
  })

  return specs
}

// ── Totals — printed vs evaluation ──────────────────────────────────────────

/** The most a student can score from ONE question of this definition.
 *  An either/or counts once; a full question is the sum of its parts. */
export function definitionWeight(qd: QuestionDefinition): number {
  const parts = qd.parts ?? []
  if (!parts.length) return Number(qd.marks ?? 0)
  return parts.reduce((s, p) => s + Number(p.marks ?? 0), 0)
}

/** Every mark this definition puts on the page, optional questions included. */
export function definitionPrinted(qd: QuestionDefinition): number {
  const count = Number(qd.count ?? 0)
  const parts = qd.parts ?? []
  const per = !parts.length
    ? Number(qd.marks ?? 0) * (qd.or_choice ? 2 : 1)
    : parts.reduce((s, p) => s + Number(p.marks ?? 0) * (p.or_choice ? 2 : 1), 0)
  return count * per
}

/** One weight per printed question in the section — a full question counts once,
 *  however many parts it has. This is what an answer rule counts. */
export function sectionWeights(section: PaperSection): number[] {
  const ws: number[] = []
  for (const qd of (section.definitions ?? [])) {
    const w = definitionWeight(qd)
    for (let i = 0; i < Math.max(0, Number(qd.count ?? 0)); i++) ws.push(w)
  }
  return ws
}

export function sectionTotals(section: PaperSection): { printed: number; evaluation: number } {
  const printed = (section.definitions ?? []).reduce((s, qd) => s + definitionPrinted(qd), 0)
  const ws = sectionWeights(section)
  const rule = section.answer_rule ?? { mode: 'ALL' }
  let evaluation: number
  if ((rule.mode ?? 'ALL').toUpperCase() === 'ANY_K') {
    const k = Math.max(0, Math.min(Number(rule.k ?? ws.length), ws.length))
    // "The most a student can score" — so the k best, when they differ.
    evaluation = [...ws].sort((a, b) => b - a).slice(0, k).reduce((s, v) => s + v, 0)
  } else {
    evaluation = ws.reduce((s, v) => s + v, 0)
  }
  return { printed, evaluation }
}

/**
 * printed    — every question that appears on the paper.
 * evaluation — the maximum a student can actually score, after every choice.
 *
 * Mirrors backend `template_totals`.
 */
export function templateTotals(def: unknown): { printed: number; evaluation: number } {
  const doc = normaliseDefinition(def)
  let printed = 0
  let evaluation = 0
  for (const sec of doc.sections) {
    const t = sectionTotals(sec)
    printed += t.printed
    evaluation += t.evaluation
  }
  return { printed, evaluation }
}

export function specCount(def: unknown, unitsIncluded: number[] = []): number {
  return compileSpecs(def, unitsIncluded).length
}

// ── Reconstruct: map a paper's questions back into its template ──────────────
// Group by the definition id stamped on each question at generation. Mirrors the
// PDF's reconstruction exactly, so the editor and the printed paper always agree.

export interface MappedPart {
  index:     number
  marks:     number
  or_choice: boolean
  /** One entry when compulsory, two when it is an either/or. */
  questions: ExamQuestion[]
}

/** One PRINTED question — what a number is spent on, and what an answer rule
 *  counts. A full question counts once however many parts it has. */
export interface MappedQuestion {
  /** Both alternatives of an either/or; a single entry otherwise. Empty when the
   *  definition has parts. */
  alternatives: ExamQuestion[]
  or_choice:    boolean
  marks:        number
  /** Populated only for a full question ("Q1 a) b) c)"). */
  parts:        MappedPart[]
}

export interface MappedDefinition {
  id:         string
  definition: QuestionDefinition
  /** The printed questions this definition contributed, in printed order. */
  questions:  MappedQuestion[]
}

export interface MappedSection {
  id:          string
  name:        string
  instruction: string
  answer_rule: AnswerRule
  definitions: MappedDefinition[]
  printed:     number
  evaluation:  number
}

export interface MappedTemplate {
  sections: MappedSection[]
  /** Legacy papers only. A non-empty value on a definition-id paper is a bug, and
   *  `error` says so rather than the UI inventing an "Other" bucket. */
  leftover: ExamQuestion[]
  error:    string | null
}

/** One entry per printed question a definition contributes, in EMISSION order —
 *  the same order `compileSpecs` produces. Walking a definition's questions
 *  against this shape reconstructs the paper without ever guessing from marks or
 *  units. Mirrors the backend's `_definition_shape`. */
interface ShapePart { index: number; alts: number; marks: number }
interface ShapeEntry { parts: ShapePart[] | null; alts: number; marks: number }

export function definitionShape(qd: QuestionDefinition): ShapeEntry[] {
  const parts = qd.parts ?? []
  const count = Math.max(0, Number(qd.count ?? 0))
  const shape: ShapeEntry[] = []

  for (let n = 0; n < count; n++) {
    if (!parts.length) {
      const marks = Number(qd.marks ?? 0)
      if (marks <= 0) continue
      shape.push({ parts: null, alts: qd.or_choice ? 2 : 1, marks })
      continue
    }
    const entries: ShapePart[] = []
    parts.forEach((p, pi) => {
      const m = Number(p.marks ?? 0)
      if (m <= 0) return
      entries.push({ index: pi, alts: p.or_choice ? 2 : 1, marks: m })
    })
    if (entries.length) shape.push({ parts: entries, alts: 1, marks: 0 })
  }
  return shape
}

export function mapQuestionsToTemplate(def: unknown, questions: ExamQuestion[]): MappedTemplate {
  const doc = normaliseDefinition(def)
  const hasIds = questions.some(q => !!q.template_block_id)

  const byDef = new Map<string, ExamQuestion[]>()
  if (hasIds) {
    for (const q of questions) {
      const key = q.template_block_id ?? ''
      byDef.set(key, [...(byDef.get(key) ?? []), q])
    }
  }

  // Legacy papers with no stamped ids are matched by (unit, marks) in document
  // order — the only path that can still leave questions over.
  const used = new Set<string>()
  const takeByMatch = (unit: number | null, marks: number, n: number): ExamQuestion[] => {
    const got: ExamQuestion[] = []
    for (const q of questions) {
      if (used.has(q.id)) continue
      if (unit != null && Number(q.unit_number) !== Number(unit)) continue
      if (Number(q.marks) !== Number(marks)) continue
      got.push(q)
      used.add(q.id)
      if (got.length >= n) break
    }
    return got
  }

  const known = new Set<string>()
  const sections: MappedSection[] = doc.sections.map((sec, si) => {
    const totals = sectionTotals(sec)
    const definitions: MappedDefinition[] = (sec.definitions ?? []).map((qd, di) => {
      const qdId = stableId(qd, 'qd', di)
      known.add(qdId)
      // An upgraded legacy block carried exactly one unit; a pool of one is that
      // unit, and an empty pool matches on marks alone.
      const legacyUnit = qd.units?.length === 1 ? qd.units[0] : null

      const pool = byDef.get(qdId) ?? []
      let pos = 0
      const take = (n: number, marks: number): ExamQuestion[] => {
        if (!hasIds) return takeByMatch(legacyUnit, marks, n)
        const got = pool.slice(pos, pos + n)
        pos += got.length
        return got
      }

      const mapped: MappedQuestion[] = []
      for (const entry of definitionShape(qd)) {
        if (entry.parts === null) {
          const alts = take(entry.alts, entry.marks)
          if (!alts.length) continue
          mapped.push({
            alternatives: alts, or_choice: entry.alts > 1, marks: entry.marks, parts: [],
          })
          continue
        }
        const parts: MappedPart[] = []
        let total = 0
        for (const p of entry.parts) {
          const alts = take(p.alts, p.marks)
          if (!alts.length) continue
          total += p.marks
          parts.push({ index: p.index, marks: p.marks, or_choice: p.alts > 1, questions: alts })
        }
        if (parts.length) {
          mapped.push({ alternatives: [], or_choice: false, marks: total, parts })
        }
      }
      return { id: qdId, definition: qd, questions: mapped }
    })
    return {
      id:          stableId(sec, 'sec', si),
      name:        sec.name,
      instruction: sec.instruction,
      answer_rule: sec.answer_rule,
      definitions,
      printed:     totals.printed,
      evaluation:  totals.evaluation,
    }
  })

  if (!hasIds) {
    return { sections, leftover: questions.filter(q => !used.has(q.id)), error: null }
  }

  const orphans = [...byDef.keys()].filter(k => !known.has(k))
  return {
    sections,
    leftover: [],
    error: orphans.length
      ? `${orphans.reduce((n, k) => n + (byDef.get(k)?.length ?? 0), 0)} question(s) reference a template definition that no longer exists in this paper's template.`
      : null,
  }
}

// ── Human-readable rule text ────────────────────────────────────────────────

const NUM_WORDS = ['ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN',
  'EIGHT', 'NINE', 'TEN', 'ELEVEN', 'TWELVE', 'THIRTEEN', 'FOURTEEN', 'FIFTEEN']

export function numWord(n: number): string {
  return NUM_WORDS[n] ?? String(n)
}

/** The instruction a section prints when the faculty typed none. */
export function defaultRuleText(section: PaperSection): string {
  const ws = sectionWeights(section)
  const rule = section.answer_rule ?? { mode: 'ALL' }
  if ((rule.mode ?? 'ALL').toUpperCase() === 'ANY_K') {
    const k = Math.max(0, Math.min(Number(rule.k ?? ws.length), ws.length))
    return `Answer any ${numWord(k)} of the following ${numWord(ws.length)} questions.`
  }
  return 'Answer ALL questions.'
}

/** Format marks without a trailing `.0`. Mirrors the backend's `_fmt`. */
export function fmtMarks(v: number): string {
  const f = Number(v)
  return Number.isInteger(f) ? String(f) : String(f)
}
