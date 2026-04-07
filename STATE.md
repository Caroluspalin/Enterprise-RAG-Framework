# Project State

Paivitetty: 2026-04-07

## Viimeksi tehty

- Phase 11 (RAG Quality & Evaluation) valmis
  - Ragas-evaluaatioputki (`scripts/evaluate.py`): Faithfulness 1.0, Answer Relevancy 0.67
  - Golden dataset: 5 TechCorp-dokumentin faktoihin perustuvaa kysymys-vastaus-paria
  - DRY-refaktorointi: SYSTEM_PROMPT ja load_llm() keskitetty `chain.py`:iin
  - Lahdeviitteet poistettu promptista (valitetaan API-metadatana, ei raakatekstina)
- Phase 10 (CI/CD) valmis: GitHub Actions, Bandit, pytest + coverage, db.py lifespan-korjaus
- README.md: CI-badge, uudet asennus- ja testiohjeet
- Projektin koko: 7 570 rivia koodia, 104 backend-testia vihrealla

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- `api.py` coverage 68 % — upload-, documents-, delete-endpointit testaamatta
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
