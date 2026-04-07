# Project State

Paivitetty: 2026-04-07

## Viimeksi tehty

- GitHub Actions CI/CD -pipeline vihreana tuotannossa (`.github/workflows/ci.yml`)
  - Laukeaa `push` ja `pull_request` -eventeilla `master`-haaraan
  - `ubuntu-latest`, Python 3.11, pip-cache
  - Asentaa `requirements.txt` + pytest, pytest-mock, pytest-cov, httpx, bandit, fpdf2
  - Bandit-tietoturvaskannaus: feilaa buildin High-tason haavoittuvuuksista
  - Pytest + coverage-raportti (XML-artifakti, 14 pv retention)
  - Dummy-ymparistomuuttujat — testit toimivat ilman oikeita API-avaimia
- Arkkitehtuurikorjaus: `db.py` ei enaa suorita `init_db()` importissa — siirretty FastAPI lifespan-eventiin (`api.py`). Poistaa import-sivuvaikutuksen joka kaatoi CI:n.
- 104 backend-testia vihrealla, kokonaiskattavuus 82 %

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- `api.py` coverage 68 % — upload-, documents-, delete-endpointit testaamatta
- CI/CD: frontend-vaihe, E2E-vaihe, branch protection ja Dependabot viela tekematta
- Frontend-testit (Vitest, Playwright) puuttuvat

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

Phase 11: LLM-vastausten evaluaatioputken (Ragas tai TruLens) perustan pystytys testikysymyksilla ja automaattisella laatumittauksella.
