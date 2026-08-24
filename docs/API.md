# LitReview REST + SSE API (v1)

Base path: `/api`. All bodies JSON, UTF-8. Operator identity: `X-Operator`
header (free-text name, attribution only — no auth). Errors return
`{"detail": "..."}` with 4xx/5xx.

All survey endpoints operate on the survey's **current version** (the
manifest tracks `current_version`).

## Surveys & dashboard

| Method & path | Body → Response |
|---|---|
| `GET /api/surveys` | → `{surveys: [Card], stats: {total, running, done, papers_analyzed}}` |
| `POST /api/surveys` | `{topic?, operator?}` → `Card` (creates v1, status `brief`) |
| `GET /api/surveys/{sid}` | → `Card` |
| `DELETE /api/surveys/{sid}` | archives (hidden from dashboard) |
| `POST /api/surveys/{sid}/versions` | `{carry: ["brief","toc","sources"]}` → `Card` (new version becomes current) |
| `PUT /api/gold-standard` | `{survey_id}` → `{ok}` (globally unique) |
| `GET /api/operators` / `POST /api/operators` | `{name}` |
| `GET /api/meta` | → `{backend, backends_available, version}` |

`Card`: `{id, topic, status, progress_pct, sources_count, chapters_done,
chapters_total, operator, updated_at, gold, current_version,
versions: [{v, status, created_at}]}`

`status` ∈ `brief | toc_pending | collecting | sources_pending | writing |
draft_pending | finalizing | done | failed | archived`.

## Brief (screen 2)

- `GET /api/surveys/{sid}/brief` → ResearchBrief JSON (spec §8.1 fields +
  `output_language, scope_preset, scope_target_pages, output_slides,
  output_podcast`).
- `PUT /api/surveys/{sid}/brief` — full replace (autosave-friendly).

## TOC (screen 3, GATE)

- `POST /api/surveys/{sid}/toc/build` — runs planner+toc_architect
  synchronously → TOC response. Status → `toc_pending`.
- `GET /api/surveys/{sid}/toc` → `{chapters: [{chapter, sections[],
  keywords_en[], description, depth}], meter: {count, ok, rule}}`
- `PUT /api/surveys/{sid}/toc` — replace chapters (drag/add/delete/edit).
- `POST /api/surveys/{sid}/toc/suggestions` → `{suggestions: [{kind, title,
  parent, reason}]}` (LLM gap-fill; purpose=toc_gaps)
- `POST /api/surveys/{sid}/toc/approve` `{notes?}` — approves GATE_TOC.
  409 if 0 chapters.

## Sources (screen 4, GATE)

- `POST /api/surveys/{sid}/sources/search` — starts S2 (hunt+audit) as a
  background job → `{job: "started"}`. Progress via SSE. 409 if TOC not
  approved or a job is running.
- `GET /api/surveys/{sid}/sources` → `{papers: [PaperRow], notices:
  {doi_failed, retracted}, approved}`
  `PaperRow`: `{paper_id, title, authors, year, language, citation_count,
  confidence, tier, doi, doi_verified, is_retracted, source, found_via,
  included}`
- `PATCH /api/surveys/{sid}/sources` `{include: [ids], exclude: [ids]}` —
  stages decisions (overlay; applied at approve).
- `POST /api/surveys/{sid}/sources/manual` `{doi?, title?}` → PaperRow
  (resolved via Crossref; 422 if unresolvable; found_via="user")
- `POST /api/surveys/{sid}/sources/approve` — applies decisions
  (excluded → `prisma.excluded_by_user`), approves GATE_SOURCES.

## Run (screen 5)

- `POST /api/surveys/{sid}/run/start` — runs the next runnable segment in
  the background (S3 after sources approve; S4 after draft approve). 409 if
  already running or a gate is pending.
- `GET /api/surveys/{sid}/run` → `{stages: [{id, title, status, started,
  ended, error}], gates: {toc, sources, draft}, running, overall_pct,
  backend, bridge_dir}`
- `GET /api/surveys/{sid}/events` — **SSE**. Events (`event:` type +
  `data:` JSON): `stage_started {stage}`, `progress {stage, detail}`,
  `log {stage, level, message}`, `stage_done {stage, duration}`,
  `stage_skipped {stage}`, `stage_failed {stage, message}`,
  `gate_reached {gate}`, `run_done {}`, `run_error {message}`.
  `id:` is a sequence number; reconnect with `Last-Event-ID` replays.

## Draft (screen 6, GATE)

- `GET /api/surveys/{sid}/draft` → `{chapters: [{index, title, confidence,
  confidence_override, issues, claims_summary {supported, uncertain,
  unsupported}, user_edited, stale_grounding, pins}], grounding_report}`
- `GET /api/surveys/{sid}/draft/chapters/{i}` → `{index, title, content,
  claims: [{id, text, citations, status, status_override, reason}],
  issues[], papers: [{n, title, apa, doi}], pins: [{id, text, status}]}`
- `PATCH .../draft/chapters/{i}` `{content}` → `{lint: [{level, message}],
  warnings: [..]}` — applies immediately; marks `user_edited`,
  `stale_grounding`; S4 marked stale.
- `PUT .../draft/chapters/{i}/confidence` `{value, reason?}` (empty value
  clears the override)
- `PUT .../draft/claims/{claim_id}` `{status, reason?}`
- `POST .../draft/chapters/{i}/pins` `{text}` → `{id}` ·
  `DELETE .../draft/chapters/{i}/pins/{pin_id}`
- `POST .../draft/rewrite` `{chapters: [i]}` — background job: revise with
  reviewer feedback + open pins → grounder → reviewer; pins → resolved.
- `POST .../draft/approve` `{force?}` — 409 with `{open_pins: [...]}` if
  open pins and not force. Approves GATE_DRAFT.

## Exports (screen 7)

- `GET /api/surveys/{sid}/exports` → `{formats: [{format, status, bytes,
  generated_at}]}`, format ∈ `html|pdf|docx|slides|podcast`, status ∈
  `idle|ready|stale|unavailable`.
- `POST /api/surveys/{sid}/exports` `{formats: [..]}` — (re)generates
  synchronously → updated statuses. PDF requires Playwright+Chromium,
  otherwise `unavailable`.
- `GET /api/surveys/{sid}/exports/{format}/download` — file response.
  `?inline=1` serves HTML viewable for the preview iframe.

## Storage layout (server side)

```
var/surveys/<sid>/manifest.json
var/surveys/<sid>/v<N>/{brief.json, state.json, run.json, overlay.json}
var/surveys/<sid>/v<N>/{bridge/, logs/stage_log.json, outputs/}
var/operators.json · var/gold.json
```
