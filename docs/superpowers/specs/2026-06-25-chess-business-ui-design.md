# Chess Tracker chess-business UI — design

**Date:** 2026-06-25
**Status:** Phase 1 design spec; no production implementation yet
**Scope:** A focused visual-identity and usefulness pass for the static Chess
Tracker dashboard.

## Goal

Make the dashboard feel like a legible, serious chess-coaching business tool:
calm, minimal, warm, and analytical. The app should read less like a generic
developer dashboard and more like a prepared private chess report built around
the user's own games.

This is not a redesign. Keep the current page map, data model, static rendering
architecture, Tabulator tables, and Lichess/Chessground board integration.

## Product Position

The target feeling is:

> Private chess coach analytics report.

The app should answer, quickly and quietly:

- What is my current chess state?
- Which openings need attention?
- What recurring leak is hurting me?
- What should I review next?

The UI should support repetition and analysis, not marketing. It should avoid
large hero sections, decorative chess imagery, animated flourish, or bright
platform-brand colors.

## Research Inputs

- Chessground is the right board foundation and should stay. It is the
  free/libre chess UI developed for Lichess, so it gives the dashboard a
  chess-native anchor rather than a custom board skin.
  Source: <https://github.com/lichess-org/chessground>
- Dashboard guidance favors at-a-glance comprehension and preattentive visual
  hierarchy: the first screen should reveal state, priority, and action without
  making users decode competing visual cues.
  Source: <https://www.nngroup.com/articles/dashboards-preattentive/>
- Text contrast must remain comfortably readable. Treat WCAG AA contrast for
  normal text as a floor, not a target.
  Source: <https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum>
- Data-viz color should maximize accessibility and harmony inside the page.
  Use a small semantic set, not broad categorical color.
  Source: <https://carbondesignsystem.com/data-visualization/color-palettes/>

## Design Principles

1. **Chess board stays central.** On opening and puzzle views, the Chessground
   board is the visual object. Surrounding UI should frame it as analysis, not
   compete with it.
2. **Color has jobs.** Do not use color for decoration. Use it for selection,
   confidence, strong stats, and action. Negative states should be carried first
   by labels, values, sort order, and neutral structure.
3. **Tables are evidence.** Tables should feel quiet, dense, scannable, and
   reliable. Avoid cardifying every row or adding badges unless they change a
   decision.
4. **Cards are summaries.** Cards should present label, value, and implication.
   They should not become mini dashboards with multiple competing treatments.
5. **The first screen should create a plan.** The landing page can remain data
   dense, but its first scan should imply today's chess work.
6. **Mobile supports review, not full analysis.** Narrow screens should keep
   KPI strips and tables usable through contained horizontal scroll. Do not
   collapse chess tables into lossy card views.

## Palette Direction

The current warm-dark palette is close. The next pass should make the layering
more deliberate without introducing a dedicated bad-signal hue. The former
terracotta alert treatment is parked until its meaning is rethought.

| Token | Proposed hex | Role |
|---|---:|---|
| `--bg` | `#211f1c` | Deep warm charcoal page background |
| `--surface` | `#2a2824` | Default panel, card, KPI strip, table hover |
| `--surface-raised` | `#312e29` | Board panel metadata, selected subpanels, open details |
| `--accent-bg` | `#352d22` | Selected rows and low-volume brass tint |
| `--text` | `#f3efe3` | Primary ivory text |
| `--muted` | `#b8b2a6` | Secondary text, table headers, labels |
| `--subtle` | `#8e887d` | Tertiary text only; avoid for small critical text |
| `--border` | `#403c35` | Hairlines and ordinary card borders |
| `--border-strong` | `#5f574b` | Focus, active controls, stronger separators |
| `--accent` | `#c4a66f` | Brass: selected, strong stat, high confidence, primary action |
| `--success` | `#9eb797` | Reserved for puzzle "correct" feedback only |
| `--board-light` | `#d8c694` | Keep current Lichess-compatible warm light square |
| `--board-dark` | `#5a5852` | Keep current Lichess-compatible dark square |
| `--piece-fg` | `#111111` | Existing piece glyph color |

### Contrast Notes

Computed against the proposed palette:

- `--text` on `--bg`: 14.30:1
- `--text` on `--surface`: 12.80:1
- `--muted` on `--surface`: 6.98:1
- `--subtle` on `--surface`: 4.18:1, so use only for non-essential tertiary
  text or larger labels.
- `--accent` on `--surface`: 6.33:1

## Color Usage Rules

Use **brass** (`--accent`) only for:

- selected table row left rule or selected board context
- strong stat cells, such as win rate at or above the existing threshold
- high-confidence dot
- recent-form KPI when the existing logic marks it positive
- primary action button
- active platform/rating state where a selected state matters

Do not use a dedicated color for bad-signal states in this phase. Existing
`alert` and `severity-*` classes can remain in the markup, but they should map
to neutral surfaces and borders. Use no color change for weak table stats unless
there is a strong product need. Shape, labels, values, and sort order should
carry negative signals.

### Parked Color Decision

The former terracotta treatment should not return until its product meaning is
specific enough to avoid reading as a generic "bad" badge. Before reintroducing
it, decide:

- whether it means urgent action, diagnostic category, user mistake, or trend
  severity
- whether it belongs on whole cards, small inline values, or only drill feedback
- how often it can appear before it stops helping scanning

## Typography Direction

Stay on the system stack unless a later explicit brand pass approves a web
font. The current static app should not gain external font dependencies in this
phase.

Recommended scale:

| Element | Size | Weight | Notes |
|---|---:|---:|---|
| Body/table text | `0.875rem` | 400 | Main reading size |
| Dense table cells | `0.84rem` | 400 | Current table density is close |
| Section heading | `1.05rem` | 650/600 | Compact, not hero-like |
| Heading helper | `0.78rem` | 400 | `--muted`, wraps under title on mobile |
| KPI label | `0.68rem` | 600 | Uppercase, moderate tracking |
| KPI value | `1.25rem` | 650/600 | Slightly less shouty than current |
| Card label | `0.7rem` | 600 | Uppercase |
| Card value | `1.25rem` | 650/600 | Same rhythm as KPI values |
| Board metadata name | `0.95rem` | 650/600 | More important than table helper text |

Rules:

- Keep `font-variant-numeric: tabular-nums` on KPI values, cards, tables,
  metadata detail rows, and deltas.
- Avoid negative letter spacing.
- Use uppercase only for labels, not body content or chess names.
- Opening names and move notation must preserve case.

## Component Rules

### KPI Strips

- Keep two strips on the landing page: Chess.com above, Lichess below.
- Both strips use the same surface, border, padding, and horizontal-scroll
  behavior.
- Profile labels are link-labels, not buttons.
- The refresh action should remain visually quiet; it is an operational action,
  not a primary chess action.

### Sections

- Sections are separated by whitespace and one hairline, not by floating cards.
- The first section has no top border.
- Helper text in headings should be lower contrast and never compete with the
  section title.
- Avoid in-app explanatory prose unless it directly helps the task.

### Cards

All summary cards should share:

- `--surface` background
- 1px `--border`
- 4px radius
- consistent padding
- label/value/subtitle rhythm

Severity and alert states should remain visually neutral in this phase. A
neutral left rule can preserve structure, but avoid card tinting for negative
states. Do not add icons for card states in this phase.

### Tables

- Tables remain evidence-dense.
- Headers use muted small type.
- Row hover uses `--surface`; selected row uses `--accent-bg` plus a brass left
  rule.
- Keep horizontal scroll wrappers for mobile.
- Do not convert opening or loss tables into mobile cards.
- Preserve `headerWordWrap: true` where headers are narrow.

### Board Panels

- Keep Chessground/Lichess board visuals.
- The board panel should feel like an analysis rail:
  - board first
  - selected line/name
  - compact stat grid
  - drill action
- Use `--surface-raised` for metadata blocks only if it improves hierarchy.
- Do not frame the board in a decorative card.

### Drill And Puzzle Views

- Puzzle feedback can use `--success` for correct feedback. Mistake feedback
  should use text weight, not a dedicated alert hue.
- Puzzle list items should share the same card grammar as behavior cards.
- Keep controls ordinary text buttons; no icon set is needed.

## Information Architecture Guidance

The strongest later product improvement would be a small "Current focus" area
on the landing page, built from existing data only. This is not required for
the immediate CSS pass, but the design should leave room for it.

Possible content:

- **Main leak:** worst active leak or "none detected"
- **Opening to review:** worst rating delta opening family
- **Next drill:** recent loss puzzle or phase issue
- **Current form:** recent-form KPI interpreted as state

This should be one compact band, not a new hero.

## Implementation Plan For Phase 2

1. Update `dashboard/styles.css` token definitions and comments to point to
   this spec.
2. Normalize component rules already present in CSS:
   KPI strips, sections, cards, Tabulator, `mqf-table`, board metadata, puzzle
   items, drill-in cards.
3. Keep template structure unchanged unless a wrapper is needed for visual
   consistency.
4. Do not change data rendering, table columns, sorting, board interaction, or
   navigation.
5. Re-run:
   - `node --check dashboard/app.js`
   - `git diff --check`
   - local browser checks for `index.html`, `opening.html`, `losses.html`
     at desktop and phone widths.

## Non-Goals

- No light theme.
- No custom web font.
- No marketing landing page.
- No new chess board skin; keep Lichess/Chessground board.
- No new JS behavior.
- No table-to-card mobile rewrite.
- No broad IA rebuild.
- No additional icon library.

## Acceptance Criteria

- The dashboard still feels minimal and warm-dark.
- Text and muted labels remain readable against their surfaces.
- Accent remains non-negative; no terracotta or generic bad-signal color is
  active.
- The first viewport feels more like a chess analysis product than a generic
  admin dashboard.
- Opening pages keep the board as the dominant visual object.
- Mobile pages avoid page-level horizontal overflow while preserving table
  utility through contained scroll.
