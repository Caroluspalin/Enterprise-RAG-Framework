# Project State

Paivitetty: 2026-04-07

## Viimeksi tehty

- **Phase 12 — Infrastructure & Security Scaling — VALMIS**
  - Kohta 1: Vektoritietokannan abstraktio (`src/vectorstore.py`) + Pinecone/Qdrant/Weaviate-adapterit, migraatioskripti, fallback, S3-backup, `VECTOR_DB_BACKEND`-env
  - Kohta 2: Audit-logitus (`audit_log`-taulu, `src/audit.py`, 8 kriittista reiittia, admin-endpoint, Audit Log -tab, account lockout)
  - Kohta 3: Tier-pohjainen rate limiting (`src/limiter.py`, FREE/PRO-tierit, per-endpoint-konfiguraatio, Redis-tuki)
  - Kohta 4: Tietoturvan koventaminen (`src/security.py`) — login rate limiting, session-invalidointi (`force_logout`), CORS-validointi, security-headerit (X-Content-Type-Options, X-Frame-Options, HSTS), dependency-auditointi CI:ssa (pip-audit + npm audit)
  - Testit: kaikki vihrealla

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- CI/CD: frontend-vaihe, E2E-vaihe, branch protection ja Dependabot viela tekematta
- Frontend-testit (Vitest, Playwright) puuttuvat
- Phase 11 jatkokehitys: golden datasetin laajennus 30 kysymykseen, context precision/recall, CI-integraatio, chunkkaus-optimointi, confidence-indikaattori

## Deployment-ymparistomuuttujat

### Render (FastAPI backend)
| Muuttuja | Kuvaus |
|---|---|
| `OPENAI_API_KEY` | OpenAI API-avain |
| `LLM_BACKEND` | LLM-valinta (openai/anthropic/ollama) |
| `ALLOWED_ORIGINS` | CORS-sallitut origot (Vercel URL) |
| `WIDGET_API_KEY` | Legacy widget-avain (siirtymakausi) |
| `PYTHON_VERSION` | Python-versio Renderilla |
| `INTERNAL_ADMIN_SECRET` | **PUUTTUU — lisaa sama arvo kuin Verceliin** |
| `VECTOR_DB_BACKEND` | Vektoritietokannan valinta (chroma/pinecone/qdrant/weaviate) |

### Vercel (Next.js frontend)
| Muuttuja | Kuvaus |
|---|---|
| `NEXT_PUBLIC_API_URL` | Render backend URL |
| `AUTH_SECRET` | NextAuth session secret |
| `BACKEND_URL` | Render backend URL (server-side) |
| `INTERNAL_ADMIN_SECRET` | **PUUTTUU — lisaa sama arvo kuin Renderiin** |
| `NEXT_PUBLIC_WIDGET_API_KEY` | Widget API-avain (julkinen, selaimessa) |

## Seuraava looginen askel

Phase 13: Advanced B2B Features & SaaS — multi-tenant-arkkitehtuuri, RBAC, monipuolinen sisallonsyotto, laskutus ja kayttorajoitukset, API-autentikaation modernisointi.
