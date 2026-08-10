---
name: gastric-literature
description: >-
  Download, index, and manage review literature for GastricTstaging (gastric US
  T-staging, EUS/CT competitors, ultrasound VLMs/agents). Uses
  docs/references/related_literature/, Unpaywall/arXiv/OpenAlex scripts, and
  optional Zotero MCP. Use when the user asks to download papers, expand the
  review corpus, sync to Zotero, search the literature library, or prepare a
  related-work / 综述 section.
---

# Gastric literature (review corpus + Zotero)

## Canonical paths

| Role | Path |
|------|------|
| PDF / abstracts | `docs/references/related_literature/articles/` |
| Priority status | `docs/references/related_literature/REVIEW_CORPUS.md` |
| Batch fetch | `docs/references/related_literature/fetch_review_corpus.py` |
| OA curl list | `docs/references/related_literature/download_pdfs.sh` |
| PubMed index (49) | `docs/references/related_literature/metadata/article_index.json` |
| Lancet set | `docs/references/lancet/` |
| Digests | `docs/mainline/nbe_ultrasound_agent_papers.html`, `nature_portfolio_gastric_ai_papers.html` |

Do **not** store large PDFs under `archive/` or invent a new `papers/` root.

## When to use what

1. **No Zotero MCP / offline OA** → run fetch scripts (below).
2. **Zotero MCP available** → search library, add-by-DOI, attach notes; still mirror important OA PDFs into `articles/` for the repo SSOT.
3. **Paywall (MDPI / Nature login)** → ask user for VPN/browser save into `articles/<slug>.pdf`; validate `%PDF` header (reject HTML).

## Download workflow

```bash
cd docs/references/related_literature
python3 fetch_review_corpus.py            # priority + Unpaywall
python3 fetch_review_corpus.py --also-index
bash download_pdfs.sh
```

After download:

- Refresh `REVIEW_CORPUS.md` counts (real PDFs only: magic `%PDF`).
- Prefer patient/project relevance: gastric T-staging, CEUS/TAUS, EUS AI, CT competitors (GTRNet/GRAPE), US-VLM/agent (Sonomate, BUSGen, Pathology-CoT).
- Skip irrelevant high-cite OpenAlex noise (general NAFLD, SVM surveys, etc.).

### Known good OA fallbacks

| Paper | Source |
|-------|--------|
| Sonomate | `https://openaccess.sgul.ac.uk/id/eprint/118201/3/s41551-025-01578-3.pdf` |
| BUSGen | arXiv `2501.06869` |
| Pathology-CoT | arXiv `2510.04587` |
| RoentGen | PMC / arXiv `2211.12737` |
| STARD-AI | DOI `10.1038/s41591-025-03953-8` |

## Zotero MCP

Installed globally: `zotero-mcp` (`uv tool install zotero-mcp-server`). Cursor launcher: `zotero-mcp-cursor` (loads `~/.config/zotero-mcp.env`).

**User must:**

1. Start **Zotero desktop**; enable local API (Settings → Advanced → allow other apps).
2. Copy `~/.config/zotero-mcp.env.example` → `~/.config/zotero-mcp.env`, fill `ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID` (for writes / add-by-DOI).
3. Reload Cursor MCP.

Suggested collection name: `GastricTstaging-review`.

When MCP tools exist, prefer:

- Search / get item / list collections
- Add by DOI for missing priority rows in `REVIEW_CORPUS.md`
- Do **not** paste API keys into chat or commit `.env`

Sync helper (after credentials exist):

```bash
python3 docs/references/related_literature/sync_review_dois_to_zotero.py --dry-run
python3 docs/references/related_literature/sync_review_dois_to_zotero.py
```

## Review writing hygiene

- Cite from disk PDFs + Zotero; keep patient-level split / no image-level leakage out of literature claims.
- Related-work buckets: (A) TAUS/CEUS staging baselines, (B) CT/EUS AI competitors, (C) US foundation / VLM / agent methods, (D) reporting (STARD-AI).
- Update digests HTML only if user asks; default is corpus + Zotero.

## MCP note

There is no built-in Semantic Scholar MCP in this workspace. Literature MCP = **Zotero** after setup. Browser MCP is last resort for paywalled PDF pages.
