# Project State

Paivitetty: 2026-04-07

## Viimeksi tehty

- Luotu `.github/workflows/ci.yml` — GitHub Actions CI/CD -pipeline
  - Kaynnistyy `push` (main) ja `pull_request` (main) -eventeilla
  - `ubuntu-latest`, Python 3.11 + pip-cache
  - Asentaa `requirements.txt` + pytest, pytest-mock, pytest-cov, httpx, bandit
  - Bandit-tietoturvaskannaus (`bandit -r src/`): feilaa buildin jos High-tason ongelmia loytyy
  - Pytest + coverage-raportti (XML-artifakti)
  - Dummy-ymparistomuuttujat (ei oikeita avaimia) — testit toimivat mockien kanssa
- Aiemmin: 104 backend-testia vihrealla, kokonaiskattavuus 82 %

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- `api.py` coverage 68 % — upload-, documents-, delete-endpointit testaamatta
- Frontend-testit (Vitest, Playwright) puuttuvat
- CI/CD: frontend-vaihe, E2E-vaihe, branch protection ja Dependabot viela tekematta

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

Phase 11: LLM-vastausten evaluaatioputken (Ragas/TruLens) perustan pystytys testikysymyksilla.
