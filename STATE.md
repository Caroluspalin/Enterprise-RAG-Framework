# Project State

Paivitetty: 2026-04-07

## Viimeksi tehty

- Phase 12, kohta 3 (Rate Limiting) valmis
  - `src/limiter.py`: In-memory sliding-window rate limiter, tier-pohjaiset rajat (FREE_USER 5/min, PRO_USER 60/min, admin = ei rajoitusta)
  - `users`-tauluun `tier`-sarake (FREE_USER | PRO_USER), migraatiologiikka olemassa oleville kannoille
  - `get_user_by_id()` -apufunktio tier-lookupia varten
  - `_resolve_tier()` ja `_apply_rate_limit()` apufunktiot `api.py`:ssa
  - Rate limit -headerit (`X-RateLimit-Limit`, `X-RateLimit-Remaining`) chat- ja upload-vastauksissa
  - HTTP 429 oikeaoppisilla headereilla kun raja ylittyy
  - `chat_client`-fixture siirretty `conftest.py`:hin (jaettu kaikkien testitiedostojen kesken)
  - 9 uutta testiä: 7 yksikkotestia (limiter-logiikka) + 2 integraatiotestia (API-taso)
  - Yhteensa 113 testia vihrealla
- Phase 12, kohta 2 (Audit-logitus) valmis
  - `audit_log`-taulu, `src/audit.py`, lokitus 8 kriittiseen reittiin, `GET /api/admin/audit-logs`
- Phase 12, kohta 1 (Vektoritietokannan abstraktio) valmis
  - `src/vectorstore.py` abstraktiokerros
- Phase 11 (RAG Quality & Evaluation) valmis
  - Ragas-evaluaatioputki, Faithfulness 1.0, Answer Relevancy 0.67
  - DRY-refaktorointi: SYSTEM_PROMPT ja load_llm() keskitetty `chain.py`:iin
- Phase 10 (CI/CD) valmis: GitHub Actions, Bandit, pytest + coverage

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- `api.py` coverage 68 % — upload-, documents-, delete-endpointit testaamatta
- CI/CD: frontend-vaihe, E2E-vaihe, branch protection ja Dependabot viela tekematta
- Frontend-testit (Vitest, Playwright) puuttuvat
- Phase 11 jatkokehitys: golden datasetin laajennus 30 kysymykseen, context precision/recall, CI-integraatio, chunkkaus-optimointi, confidence-indikaattori
- Slowapi-limiter on viela mukana rinnakkain uuden tier-limiterin kanssa — voidaan poistaa myohemmin

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

Phase 12, kohta 4: Tietoturvan koventaminen — login rate limiting, session-invalidointi, CORS-validointi, security-headerit, dependency-auditointi CI:ssa.
