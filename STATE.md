# Project State

Paivitetty: 2026-04-07

## Viimeksi tehty

- Phase 11 evaluaatioputki valmis (`scripts/evaluate.py`)
  - Ragas-integraatio: Faithfulness + Answer Relevancy -metrikat
  - Eksplisiittinen LLM (ChatOpenAI gpt-4o) ja embedding-malli (text-embedding-3-small) Ragasille
  - Golden dataset: 5 TechCorp-dokumentin faktoihin perustuvaa kysymys-vastaus-paria
  - Tulokset tallennetaan `eval_results.json` -tiedostoon
  - Faithfulness: 1.0 (taydellinen), Answer Relevancy: numeerinen tulos (ei enaa NaN)
- Phase 10 CI/CD vihreana: GitHub Actions (`ci.yml`), Bandit-skannaus, pytest + coverage
- Arkkitehtuurikorjaus: `db.py` init_db() siirretty FastAPI lifespan-eventiin
- README.md paivitetty: CI-badge, uudet asennus- ja testiohjeet

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- `api.py` coverage 68 % — upload-, documents-, delete-endpointit testaamatta
- CI/CD: frontend-vaihe, E2E-vaihe, branch protection ja Dependabot viela tekematta
- Frontend-testit (Vitest, Playwright) puuttuvat
- Phase 11 keskeneraiset: golden datasetin laajennus 30 kysymykseen, context precision/recall -metrikat, CI-integraatio

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

### Vercel (Next.js frontend)
| Muuttuja | Kuvaus |
|---|---|
| `NEXT_PUBLIC_API_URL` | Render backend URL |
| `AUTH_SECRET` | NextAuth session secret |
| `BACKEND_URL` | Render backend URL (server-side) |
| `INTERNAL_ADMIN_SECRET` | **PUUTTUU — lisaa sama arvo kuin Renderiin** |
| `NEXT_PUBLIC_WIDGET_API_KEY` | Widget API-avain (julkinen, selaimessa) |

## Seuraava looginen askel

Phase 12: Infrastructure & Security Scaling — vektoritietokannan abstraktiokerros, audit-logitus, rate limiting -parannus ja tietoturvan koventaminen.
