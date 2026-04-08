# Project State

Paivitetty: 2026-04-08

## Viimeksi tehty

- **Phase 14 — Frontend API Migration — VALMIS & COMMITOITU**
  - `frontend/lib/api.ts`: kaikki fetch-polut päivitetty `/api/v1/*` -muotoon (9 polkua)
  - `frontend/lib/admin.ts`: kaikki `${BACKEND_URL}/api/admin/*` ja `/api/auth/register` päivitetty `/api/v1/*`-muotoon
  - `frontend/auth.ts`: login-URL päivitetty `/api/v1/auth/login`-muotoon
  - `frontend/next.config.ts`: kaikki rewrite-säännöt päivitetty `source` ja `destination` `/api/v1/*`-polkuihin (10 sääntöä)
  - `frontend/public/widget.js`: SSE-endpoint päivitetty `/api/v1/chat`-muotoon
  - BFF-reitit (`frontend/app/api/`): tarkistettu — eivät sisällä suoria FastAPI-URL:eja, käyttävät `admin.ts`-funktioita

- **Phase 13 — Advanced B2B Features & SaaS — VALMIS & COMMITOITU**
  - Kohta 1: Tietokannan ja vektorikannan tenant-isolaatio
  - Kohta 2: API-tason tenant-isolaatio
  - Kohta 3: RBAC (Role-Based Access Control)
  - Kohta 4: Tier-pohjainen laskutus ja käyttöseuranta
  - Kohta 5: API-versiointi + JWT-autentikaatio + Stripe webhook-valmius

- **Bugikorjaukset**
  - `frontend/components/UsersTab.tsx`: rooli-dropdown päivitetty vanhoista `"user"/"admin"` arvoista RBAC-hierarkiaan (`member`/`admin`/`viewer`/`owner`) — poisti `CHECK constraint failed` -virheen
  - `src/vectorstore.py`: automaattinen migraatio vanhoille chunkeille joilta puuttui `tenant_id` — dokumentit näkyvät nyt listassa
  - `frontend/components/Sidebar.tsx`: ei enää kutsu `/api/v1/documents` ennen käyttäjän tunnistamista — poisti turhan 403-virheen

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei vielä testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkötestit puuttuvat
- CI/CD: frontend-vaihe, E2E-vaihe, branch protection ja Dependabot vielä tekemättä
- Frontend-testit (Vitest, Playwright) puuttuvat
- Frontend-roolinäkyvyys (RBAC Phase 15): navigaatio ja UI-elementit eivät vielä piilota/näytä toimintoja roolin mukaan
- Organisaation hallintapaneeli (Phase 17): omistaja ei vielä voi kutsua käyttäjiä tai nähdä käyttötilastoja
- Stripe-integraatio: webhook kuuntelee mutta ei vielä käsittele subscription-eventtejä
- **Session-invalidointi (force_logout) EI TOTEUTETTU** — `force_logout`-kenttää ei ole users-taulussa eikä API:ssa
- **Redis rate limiting EI TOTEUTETTU** — `limiter.py` on pelkästään in-memory
- Dokumentti- ja tallennustilarajat puuttuvat — billing gate valvoo vain API-kutsumäärää, ei dokumenttimäärää
- Manuaalinen smoke-testi tuotannossa vielä tekemättä (login, chat, upload, admin-paneeli)

## Deployment-ympäristömuuttujat

### Render (FastAPI backend)
| Muuttuja | Kuvaus |
|---|---|
| `OPENAI_API_KEY` | OpenAI API-avain |
| `LLM_BACKEND` | LLM-valinta (openai/anthropic/ollama) |
| `ALLOWED_ORIGINS` | CORS-sallitut origot (Vercel URL) |
| `WIDGET_API_KEY` | Legacy widget-avain (siirtymäkausi) |
| `PYTHON_VERSION` | Python-versio Renderilla |
| `INTERNAL_ADMIN_SECRET` | **PUUTTUU — lisää sama arvo kuin Verceliin** |
| `VECTOR_DB_BACKEND` | Vektoritietokannan valinta (chroma/pinecone/qdrant/weaviate) |
| `JWT_SECRET` | **UUSI** — JWT-allekirjoitusavain (min 32 satunnaista merkkiä) |
| `STRIPE_WEBHOOK_SECRET` | **UUSI** — Stripe webhook signing secret (whsec_...) |

### Vercel (Next.js frontend)
| Muuttuja | Kuvaus |
|---|---|
| `NEXT_PUBLIC_API_URL` | Render backend URL |
| `AUTH_SECRET` | NextAuth session secret |
| `BACKEND_URL` | Render backend URL (server-side) |
| `INTERNAL_ADMIN_SECRET` | **PUUTTUU — lisää sama arvo kuin Renderiin** |
| `NEXT_PUBLIC_WIDGET_API_KEY` | Widget API-avain (julkinen, selaimessa) |

## Seuraava looginen askel

1. **Manuaalinen smoke-testi**: login, chat, upload, admin-paneeli tuotannossa
2. **Phase 15**: Frontend RBAC-näkyvyys + session-invalidointi
3. **Phase 16**: Stripe subscription events + dokumenttirajoitukset + usage dashboard
4. **Phase 17**: Org & team management (kutsu, roolit, jäsenlista)
5. **Phase 18**: Frontend-testit (Vitest, Playwright) + CI/CD viimeistely
6. **Phase 19**: Tuotannon koventaminen (WAL, health check, retry, SSE keep-alive)
