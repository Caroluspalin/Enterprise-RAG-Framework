# Build Roadmap

### Phase 1 — Project Scaffold
- [x] Create directory structure (`docs/`, `src/`, `chroma_db/`)
- [x] Write `requirements.txt`
- [x] Write `.env.example`
- [x] Initialize git repository and add `.gitignore` (exclude `chroma_db/`, `.env`, `docs/`)

### Phase 2 — Document Ingestion (`src/ingest.py`)
- [x] Recursively discover all `.pdf` files under `DOCS_PATH`
- [x] Load each PDF with `PyPDFLoader`
- [x] Split documents into chunks with `RecursiveCharacterTextSplitter`
- [x] Generate embeddings (OpenAI `text-embedding-3-small` or local)
- [x] Persist chunks and embeddings to ChromaDB
- [x] Print ingestion summary (files processed, chunks stored)
- [x] Add `--reset` flag to wipe and re-ingest from scratch

### Phase 3 — Retriever (`src/retriever.py`)
- [x] Load the persisted ChromaDB collection
- [x] Expose a `get_retriever(k: int)` function returning a LangChain `VectorStoreRetriever`
- [ ] Optionally add metadata filtering (e.g. by filename or date)

### Phase 4 — RAG Chain (`src/chain.py`)
- [x] Write a system prompt that instructs the LLM to answer only from provided context
- [x] Build a `RetrievalQA` or `ConversationalRetrievalChain` using the retriever
- [x] Include source document metadata (filename, page number) in the response
- [x] Support swappable LLM backends via environment variable (`OPENAI`, `ANTHROPIC`, `OLLAMA`)

### Phase 5 — Terminal Chat Interface (`src/chat.py`)
- [x] Print startup banner with loaded document count
- [x] Run an input loop: read question → invoke chain → print answer + sources
- [x] Handle `/exit`, `/reset`, `/list` commands
- [x] Maintain conversation history for follow-up questions

### Phase 6 — Quality & Hardening
- [x] Add chunk deduplication (skip re-ingesting unchanged files via content hash)
- [x] Add logging to file for debugging ingestion and retrieval
- [x] Evaluate retrieval quality with a small test question set
- [ ] Tune `CHUNK_SIZE`, `CHUNK_OVERLAP`, and `TOP_K` based on evaluation

### Phase 7 — Web UI (Next.js + FastAPI)
- [x] FastAPI backend (`src/api.py`) with SSE streaming, PDF upload, document list endpoints
- [x] Next.js 15 frontend scaffold (App Router, Tailwind CSS, TypeScript)
- [x] Chat UI: streaming message bubbles, blinking cursor, auto-scroll
- [x] PDF upload panel with drag-and-drop in the sidebar
- [x] Source citation chips displayed below each assistant message
- [x] Document list in sidebar (live-refreshed after upload)
- [x] Markdown rendering in assistant messages (react-markdown + remark-gfm + rehype-highlight)
- [x] Mobile-responsive layout (slide-over sidebar, hamburger menu, wider bubbles)

### Phase 7b — Chat History & Analytics Foundation
- [x] SQLite database module (`src/db.py`) with `sessions` and `messages` tables
- [x] CRUD functions: create/get/list/delete sessions, add/get messages
- [x] Auto-title sessions from first user question
- [x] API endpoints: POST/GET/DELETE `/api/chat/sessions`, GET `/api/chat/sessions/{id}`
- [x] Chat endpoint (`POST /api/chat`) auto-persists Q&A when `session_id` is provided
- [x] Frontend: session management, history sidebar, load past conversations
- [x] Analytics dashboard (message counts, popular questions, usage over time)

### Phase 8 — Embeddable Chat Widget
- [x] Standalone `/widget` route (full-screen chat, no sidebar, no auth)
- [x] `embed-test.html` demo page with floating iframe toggle
- [x] Disable Next.js dev indicator so it does not overlap widget input
- [x] Configurable widget theme (colors, title) via query params (?title=, ?accent=, ?bg=)
- [x] Origin allowlist for iframe embedding (CSP frame-ancestors via middleware + WIDGET_ALLOWED_ORIGINS env)
- [x] `widget.js` — standalone embeddable script (vanilla JS, Shadow DOM, zero dependencies)
- [x] One-line `<script>` integration for any external website
- [x] SSE streaming direct to FastAPI backend with X-Widget-Key auth
- [x] SessionStorage-based session persistence (chat history across page navigations)
- [x] Safe text rendering (no innerHTML, XSS-proof, basic Markdown support)
- [x] ARIA attributes, keyboard navigation (Enter/Escape), screen reader support
- [x] Mobile-responsive (full-screen on small viewports)
- [x] Typing indicator (animated dots), error banners, rate-limit handling
- [x] Configurable via data-* attributes (api, key, title, accent, bg, position)

### Phase 9 — User Management & Auth Hardening
- [x] `users` table in SQLite with bcrypt password hashing
- [x] CRUD functions: create_user, verify_user, get_user_by_username, list_users
- [x] Default admin seed on first run (`admin` / `admin123` — change immediately)
- [x] `POST /api/auth/login` — verify credentials against hashed passwords
- [x] `POST /api/auth/register` — create new users with bcrypt hashing
- [x] `auth.ts` calls FastAPI backend instead of hardcoded demo users
- [x] `BACKEND_URL` env var for server-side auth calls
- [x] `GET /api/analytics` endpoint with message counts, per-day stats, popular & recent questions
- [x] Admin panel analytics tab with stat cards, bar chart, question lists
- [x] `api_keys` table with SHA-256 hashed keys, per-user, revocable
- [x] `INTERNAL_ADMIN_SECRET` server-to-server auth for admin endpoints
- [x] `GET/DELETE /api/admin/users` — list and delete users (admin only)
- [x] `POST /api/admin/users/{id}/change-password` — password change (admin only)
- [x] `POST/GET/DELETE /api/admin/api-keys` — create, list, revoke API keys (admin only)
- [x] `/api/chat` validates X-Widget-Key against DB-stored keys (with legacy env var fallback)
- [x] Admin panel user management UI (list / create / delete users)
- [x] Admin panel API key management UI (generate / revoke)
- [x] Password change UI
- [x] Toast notification system for all CRUD operations
- [x] Next.js BFF layer (`lib/admin.ts`) — server-to-server, secret never exposed to browser

---

### Phase 10 — Production Resilience & CI/CD

> Tavoite: Yksikään rikkinäinen commit ei pääse tuotantoon. Jokainen regressio havaitaan automaattisesti ennen deployta.

**Backend-testit (pytest + httpx)**
- [x] Luo `tests/` -hakemisto ja `pyproject.toml` pytest-konfiguraatiolla
- [x] Yksikkötestit `db.py`:lle: käyttäjä-CRUD, sessiot, viestit, API-avainten hash-validointi (in-memory SQLite)
- [x] Integraatiotestit `api.py`:lle — autentikaatio-endpointit, admin-endpointit (`INTERNAL_ADMIN_SECRET`-validointi), session-CRUD, health check (50 testiä, kaikki vihreällä)
- [x] Yksikkötestit `chain.py`:lle: prompt-template, LLM-backend-valinta, invoke_chain, format_sources, build_chain (13 testiä, coverage 100 %)
- [x] Integraatiotestit `api.py` `/api/chat` -endpointille: SSE-virran parsinta, session-persistointi, auto-title, widget API key -validointi, chat-historia (13 testiä)
- [x] Yksikkötestit `ingest.py`:lle: PDF-lataus (fpdf2), chunkkaus (oikea RecursiveCharacterTextSplitter), overlap-validointi, deduplikaatio, `--reset`, reunatapaukset (tyhjä kansio, ei-PDF-tiedostot), metadata (28 testiä, coverage 92 %)
- [ ] Yksikkötestit `retriever.py`:lle: `get_retriever()` palauttaa toimivan retrieverin, `TOP_K`-konfiguraatio vaikuttaa tuloksiin
- [x] Testikattavuusraportti (`pytest-cov`) — kokonaiskattavuus 82 % (tavoite 80 % saavutettu)

**Frontend-testit**
- [ ] Vitest + React Testing Library -konfiguraatio (`vitest.config.ts`, `setup.ts`)
- [ ] Yksikkötestit kriittisille komponenteille: `ChatWindow`, `MessageBubble` (markdown-renderöinti), `AdminPanel` (tab-navigointi), `Toast` (ilmoitusten lifecycle)
- [ ] Yksikkötestit `lib/api.ts`:lle: fetch-wrapperin virheenkäsittely, SSE-parsinta, response-validointi
- [ ] Yksikkötestit `lib/admin.ts`:lle: `unwrap<T>`-funktio, header-injektio, virhekäsittely
- [ ] E2E-testit (Playwright): login-flow, chat-viesti lähetetään ja vastaus renderöityy, session-historia latautuu, admin-paneelin tab-navigointi, PDF-upload, widget-näkymä latautuu

**CI/CD-pipeline (GitHub Actions)**
- [x] Luo `.github/workflows/ci.yml`: käynnistyy `push`- ja `pull_request`-eventeillä
- [x] Backend-vaihe: Python-setup, `pip install`, `pytest --cov` — pipeline feilaa jos testit eivät mene läpi
- [x] Tietoturvaskannaus: Bandit (`bandit -r src/`) — feilaa buildin High-tason haavoittuvuuksista
- [x] Dummy-ympäristömuuttujat CI:lle — testit toimivat ilman oikeita API-avaimia
- [x] Coverage- ja Bandit-raportit GitHub-artifakteina (14 pv retention)
- [x] Import-sivuvaikutuksen korjaus: `db.py` ei enää aja `init_db()` importissa — siirretty FastAPI lifespan-eventiin
- [ ] Frontend-vaihe: Node-setup, `npm ci`, `npm run lint`, `vitest run`, `npm run build` — pipeline feilaa jos buildi ei onnistu
- [ ] E2E-vaihe: Playwright-testit headless-chromella (ajetaan vain `main`-branchissa tai PR-mergessä)
- [ ] Branch protection -sääntö: `main`-branchiin ei voi pushata ilman vihreää CI-statusta
- [ ] Dependabot tai Renovate -konfiguraatio riippuvuuspäivitysten automatisointiin

**Tuotannon resilienssi**
- [ ] Retry-logiikka `lib/api.ts`:ään: exponentiaalisesti kasvava backoff (max 3 yritystä) OpenAI/LLM-kutsujen epäonnistuessa
- [ ] Retry-logiikka `chain.py`:ään: LLM-kutsun uudelleenyritys transienttien virheiden varalta (`RateLimitError`, `APIConnectionError`)
- [ ] SSE-yhteyden uudelleenmuodostus frontendissä: jos stream katkeaa kesken vastauksen, näytä käyttäjälle virheilmoitus ja "Yritä uudelleen" -painike
- [ ] Graceful degradation: jos ChromaDB ei ole tavoitettavissa, palauta selkeä virheilmoitus eikä 500-stacktrace
- [ ] SQLite-yhteyksien hallinta: WAL-moodi (`PRAGMA journal_mode=WAL`) ja connection pooling (`check_same_thread=False`) samanaikaisten pyyntöjen tueksi
- [ ] Health check -endpoint (`GET /api/health`): tarkistaa SQLite-, ChromaDB- ja LLM-yhteydet; Render voi käyttää tätä uptime-monitorointiin
- [ ] Vercel-timeout-mitigaatio: pitkäkestoiset LLM-vastaukset SSE-streamina (jo toteutettu), mutta lisää keep-alive -kommenttirivit streamiin jotta Vercel ei katkaise yhteyttä 30 s kohdalla

---

### Phase 11 — RAG Quality & Evaluation (Kriittinen)

> Tavoite: B2B-tuote ei saa hallusinoida. Jokainen vastaus on mitattavissa, ja laatu paranee systemaattisesti dataohjautuvasti.

**Käyttäjäpalaute-mekanismi (thumbs up/down)**
- [ ] Uusi `feedback`-taulu SQLiteen: `id`, `message_id` (FK → messages), `session_id`, `rating` (1 = hyvä, -1 = huono), `comment` (vapaaehtoinen tekstikenttä), `created_at`
- [ ] `POST /api/chat/messages/{id}/feedback` -endpoint: tallentaa arvion tietokantaan
- [ ] `GET /api/analytics/feedback` -endpoint: palauttaa aggregoidun palautedatan (% positiivinen, huonoimmat vastaukset, trendi ajan yli)
- [ ] Frontend: 👍/👎 -painikkeet jokaisen assistant-viestin alle (`MessageBubble`-komponentti)
- [ ] Admin-paneeliin uusi "Quality"-tab: huonoiten arvioidut vastaukset, palautetrendi, mahdollisuus tarkastella yksittäistä keskustelua kontekstissa

**Automatisoitu evaluaatio-pipeline**
- [x] Evaluaatioskripti (`scripts/evaluate.py`): ajaa golden set -kysymykset RAG-ketjun läpi ja laskee metrikat
- [x] Metrikat: answer relevancy (vastauksen osuvuus), faithfulness (vastaus perustuu kontekstiin, ei hallusinoi)
- [x] Ragas-integraatio metrikoiden laskentaan (LangchainLLMWrapper + LangchainEmbeddingsWrapper)
- [x] Golden dataset: 5 TechCorp-dokumentin faktoihin perustuvaa kysymys-vastaus-paria
- [x] Evaluaatioraportti tallennetaan JSON-muotoon (`eval_results.json`): jokainen kysymys, saatu vastaus, metrikat
- [ ] Golden datasetin laajentaminen 30 kysymykseen kattamaan kaikki dokumenttien osa-alueet
- [ ] Lisämetrikat: context precision, context recall
- [ ] GitHub Actions -integraatio: evaluaatio ajetaan CI:ssä ja raportti arkistoidaan artifaktina; pipeline varoittaa (mutta ei feilaa) jos faithfulness-keskiarvo laskee alle kynnysarvon

**Chunkkaus-strategian optimointi**
- [ ] Parametrisoitu benchmark-skripti: ajaa golden setin eri `CHUNK_SIZE` (500, 750, 1000, 1500) × `CHUNK_OVERLAP` (50, 100, 200, 300) × `TOP_K` (3, 5, 8, 10) -yhdistelmillä
- [ ] Tulokset tallennetaan CSV-muotoon: parametrit, metrikat, latenssi, chunkkien määrä
- [ ] Dokumentoi optimaalinen konfiguraatio ja lukitse se `.env.example`-tiedostoon perusteluineen
- [ ] Embedding-mallin vertailu: `text-embedding-3-small` vs `text-embedding-3-large` — mittaa laatuero vs. kustannus ja latenssi

**Hallusinaatioiden torjunta**
- [x] System promptin päivitys: eksplisiittinen "jos konteksti ei riitä, sano se" -ohjeistus + lähdeviitteiden poisto promptista (metadata via API). Faithfulness 1.0.
- [x] DRY-refaktorointi: SYSTEM_PROMPT ja load_llm() keskitetty `chain.py`:iin — api.py ja evaluate.py käyttävät samaa totuuden lähdettä
- [ ] Confidence-indikaattori: jos retriever palauttaa chunkit joiden similarity score on matala (alle kynnysarvon), lisää vastaukseen varoitus
- [ ] Source verification UI: jokaisen vastauksen lähdeviittaukset ovat klikattavia ja näyttävät alkuperäisen chunk-tekstin

---

### Phase 12 — Infrastructure & Security Scaling

> Tavoite: Tuotantoinfrastruktuuri kestää yritysasiakkaiden kuorman, data on turvassa, ja jokainen operaatio on jäljitettävissä.

**Vektoritietokannan migraatio**
- [x] Abstraktiokerros: `src/vectorstore.py` joka piilottaa ChromaDB:n taakse yhtenäisen rajapinnan (`add_documents`, `search`, `delete_collection`, `backup`)
- [x] Pinecone/Qdrant/Weaviate -adapteri: valitse yksi hallinnoitu palvelu ja toteuta adapteri abstraktiokerroksen taakse
- [x] Migraatioskripti: lukee olemassa olevan ChromaDB-kokoelman ja siirtää kaikki dokumentit + metadata hallinnoiduun kantaan
- [x] Fallback-strategia: jos hallinnoitu palvelu ei ole tavoitettavissa, sovellus voi toimia read-only-tilassa lokaalista cachesta
- [x] ChromaDB S3-varmuuskopiointi (vaihtoehto hallinnoidulle palvelulle): automaattinen snapshot `chroma_db/`-hakemistosta S3:een cron-ajoituksella tai API-kutsulla
- [x] `VECTOR_DB_BACKEND`-ympäristömuuttuja: `chroma` (oletus) | `pinecone` | `qdrant` | `weaviate`

**Audit-logitus**
- [x] Uusi `audit_log`-taulu: `id`, `timestamp`, `user_id`, `action`, `ip_address`, `details` (JSON)
- [x] `src/audit.py` -moduuli: `log_event()` ja `get_audit_logs()` -funktiot
- [x] Audit-logging `api.py`:ssä: LOGIN_SUCCESS/FAILED, USER_CREATED/DELETED, PASSWORD_CHANGED, DOC_UPLOADED/DELETED, API_KEY_CREATED/REVOKED
- [x] `GET /api/admin/audit-logs` -endpoint: admin-suojattu, limit-parametri, uusimmat ensin
- [x] Admin-paneeliin "Audit Log" -tab: kronologinen lista tapahtumista, filtterit, CSV-export
- [x] Epäonnistuneiden kirjautumisyritysten seuranta: jos sama IP/käyttäjätunnus epäonnistuu 5 kertaa 15 minuutissa, lukitse tilapäisesti (account lockout)

**Rate limiting -parannus**
- [x] Tier-pohjainen in-memory rate limiter: `src/limiter.py` (sliding window, thread-safe)
- [x] `users`-tauluun `tier`-sarake: `FREE_USER` (5/min) | `PRO_USER` (60/min), admin = ei rajoitusta
- [x] Käyttäjäkohtainen rate limiting: user_id tai IP avaimena, tier DB:stä
- [x] Rate limit -headerit vastauksissa: `X-RateLimit-Limit`, `X-RateLimit-Remaining`
- [x] Rajoitus `POST /api/chat` ja `POST /api/upload` -endpointeissa
- [x] 9 uutta testiä (7 yksikkö + 2 integraatio), yhteensä 113 testiä vihreällä
- [x] Rate limit -konfiguraatio per endpoint: admin-endpointeille tiukemmat rajat kuin chat-endpointille
- [ ] Redis-pohjainen rate limiting (valinnainen): kun siirrytään useampaan API-instanssiin, in-memory slowapi ei riitä

**Tietoturvan koventaminen**
- [x] Login-yrityksen rate limiting: `slowapi`-rajoitus `/api/auth/login`-endpointille (max 10/minuutti per IP)
- [ ] Session-invalidointi: admin voi pakottaa käyttäjän uloskirjautumisen (`force_logout`-kenttä users-tauluun, tarkistetaan jokaisessa pyynnössä)
- [x] CORS-konfiguraation validointi: varmista ettei `ALLOWED_ORIGINS` sisällä `*` tuotannossa (lisää startup-varoitus)
- [x] Helmet-tyyppiset security-headerit: `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` FastAPI-middleware-tasolla
- [x] Dependency-auditointi: `pip-audit` ja `npm audit` CI-pipelineen — pipeline feilaa kriittisistä haavoittuvuuksista

---

### Phase 13 — Advanced B2B Features & SaaS

> Tavoite: Tuotteesta tulee moniasiakasympäristö, jossa jokainen organisaatio hallinnoi omia dokumenttejaan, käyttäjiään ja laskutustaan.

**Multi-tenant-arkkitehtuuri**
- [x] `organizations`-taulu: `id`, `name`, `created_at`
- [x] `users`-tauluun `organization_id` (FK → organizations) — jokainen käyttäjä kuuluu yhteen organisaatioon
- [x] Organisaatiokohtaiset vektorikokoelmat: tenant_id-metatietofiltteröinti ChromaDB:ssä (ei erillisiä collectioneja)
- [x] Tenant-isolaatio: `_resolve_tenant_id()` jokaisessa pyynnössä, retriever scoped per tenant
- [x] API-avaimet sidottu organisaatioon: `api_keys`-tauluun `organization_id`, widget näkee vain oman orgin dokumentit
- [ ] Organisaation hallintapaneeli: omistaja voi kutsua käyttäjiä, hallita rooleja, nähdä käyttötilastot

**RBAC (Role-Based Access Control)**
- [x] Roolien laajennus: `owner` (organisaation omistaja), `admin` (hallinnoi käyttäjiä ja dokumentteja), `member` (chat + omat sessiot), `viewer` (vain luku)
- [x] Roolikohtaiset endpointit: `require_role()` FastAPI Depends-dekoraattori joka tarkistaa roolin automaattisesti
- [x] API-avainten RBAC: `api_keys.role`-sarake, avaimet noudattavat samoja rajoituksia kuin käyttäjät
- [ ] Frontend-roolinäkyvyys: navigaatio ja UI-elementit piilottavat/näyttävät toiminnot roolin mukaan

**Monipuolinen sisällön syöttö**
- [ ] URL-pohjainen sisällön indeksointi: käyttäjä antaa URL-osoitteen → backend hakee sivun, parsii tekstin (BeautifulSoup/Trafilatura), chunkkaa ja indeksoi
- [ ] Notion-integraatio: OAuth-yhteys Notion-workspaceen, sivujen automaattinen synkronointi vektoritietokantaan
- [ ] Confluence-integraatio: API-avainpohjainen yhteys, sivujen haku ja indeksointi
- [ ] Tiedostomuotojen laajennus: Word (.docx), PowerPoint (.pptx), Excel (.xlsx), Markdown (.md), pelkkä teksti (.txt)
- [ ] Dokumenttien uudelleenindeksointi admin-paneelista: "Re-index" -painike joka ajaa ingestion uudelleen valituille dokumenteille
- [ ] Metadata-filtteröinti haussa: käyttäjä voi rajata haun tiettyyn dokumenttiin, aikaväliin tai tagiin

**Laskutus ja käyttörajoitukset**
- [x] API-kutsujen laskuri per organisaatio: `api_calls_count` organizations-taulussa, `usage_logs`-taulu jokaisesta kutsusta kirjaa timestampin, tokenimäärän ja endpointin
- [x] API-kutsurajoitukset (billing gate): `src/billing.py` + `check_and_track_usage()`; HTTP 402 kun free (100/kk) tai pro (10 000/kk) kiintiö täynnä, enterprise = rajaton; 26 testiä vihreällä
- [ ] Dokumentti- ja tallennustilarajat: free = 5 dokumenttia, pro = 100 dokumenttia (kutsulaskuri toteutettu, mutta dokumenttimäärä- ja tallennustilarajoja ei vielä valvota)
- [ ] Stripe-integraatio: subscription-pohjainen laskutus (free / pro / enterprise -tasot), maksutapahtumien käsittely webhook-kuuntelijassa
- [ ] Usage dashboard: organisaation omistaja näkee reaaliaikaisen käyttötilanteen ja laskutushistorian
- [ ] Automaattinen ilmoitus kun käyttöraja lähestyy (80 %) ja kun se ylittyy

**API-autentikaation modernisointi**
- [x] JWT-pohjainen autentikaatio: `src/jwt_auth.py` (HS256, PyJWT), `make_access_token` + `decode_access_token`; `rbac.resolve_role()` hyväksyy JWT Bearer tokenin ennen API-avainta
- [x] API-versiointi: kaikki reitit siirretty `/api/v1/*` alle FastAPI `APIRouter(prefix="/api/v1")`; kaikki 199 → 223 testiä päivitetty uusille reiteille
- [x] Webhook-valmius: `POST /api/v1/webhooks/stripe` validoi Stripe-allekirjoituksen HMAC-SHA256:lla (`STRIPE_WEBHOOK_SECRET`); palauttaa HTTP 200; 6 testia
- [ ] Täydellinen Stripe-integraatio: subscription-eventtien käsittely (upgrade/downgrade/cancel) webhook-kuuntelijassa

---

### Phase 14 — Frontend API Migration (Kriittinen bugikorjaus)

> Tavoite: Frontend puhuu uusille `/api/v1/`-reiteille. Ilman tätä koko UI on rikki tuotannossa.

- [x] `frontend/lib/api.ts` — päivitä `/api/chat`, `/api/documents`, `/api/chat/sessions`, `/api/upload` → `/api/v1/*`
- [x] `frontend/lib/admin.ts` — päivitä kaikki `${BACKEND_URL}/api/admin/*` ja `/api/auth/register` → `/api/v1/*`
- [x] `frontend/auth.ts` — päivitä `/api/auth/login` → `/api/v1/auth/login`
- [x] `frontend/app/api/` BFF-reitit — tarkistettu; käyttävät `admin.ts`-funktioita, ei suoria FastAPI-URL:eja
- [x] `frontend/next.config.ts` — päivitetty kaikki rewrite-säännöt `/api/v1/`-polkuihin (löytyi tarkistuksessa)
- [x] `frontend/public/widget.js` — päivitä hardkoodattu `/api/chat` → `/api/v1/chat`
- [ ] Manuaalinen smoke-testi: login, chat, upload, admin-paneeli toimii deployn jälkeen

---

### Phase 15 — Frontend RBAC-näkyvyys & Session-turvallisuus

> Tavoite: UI:ssa ei näy nappeja joita käyttäjällä ei ole oikeutta painaa. Admin voi pakottaa uloskirjautumisen.

- [ ] `Sidebar.tsx` ja navigaatio — piilota upload-painike viewer- ja member-käyttäjiltä
- [ ] `AdminPanel.tsx` — suojaa admin-paneelin reitti roolilla (`owner` / `admin` only); muut saavat 403-näkymän
- [ ] `MessageBubble.tsx` / `ChatInput.tsx` — estä chat-input viewer-roolilla (tai piilota kokonaan)
- [ ] Rooli välitetty NextAuth-sessioniin — `role`-kenttä `session.user`-objektissa, käytettävissä kaikissa komponenteissa
- [ ] Session-invalidointi (`force_logout`): lisää `force_logout`-kenttä `users`-tauluun, tarkista se `resolve_role()`-funktiossa, NextAuth-session päättyy pakotetusti

---

### Phase 16 — Stripe-integraatio & Laskutus

> Tavoite: Organisaatiot maksavat oikeasti. Plan-muutokset päivittyvät automaattisesti.

- [ ] Stripe Customer Portal -linkki admin-paneeliin (omistaja hallinnoi tilaustaan itse)
- [ ] Webhook-eventtien käsittely: `customer.subscription.updated` → päivitä `subscription_plan` kannassa; `customer.subscription.deleted` → pudota `free`-tasolle
- [ ] `stripe_customer_id` tallennetaan `organizations`-tauluun rekisteröinnin yhteydessä
- [ ] Dokumenttimääräraja: free = max 5 dokumenttia, pro = max 100; tarkistus `POST /api/v1/upload` -endpointissa (HTTP 402 rajan ylittyessä)
- [ ] Automaattinen sähköposti-/webhook-ilmoitus kun kiintiö on 80 % täynnä
- [ ] Usage dashboard -komponentti admin-paneeliin: nykyinen kuukausikäyttö vs. kiintiö, laskutushistoria

---

### Phase 17 — Org & Team Management

> Tavoite: Organisaation omistaja hallinnoi tiimiään itse ilman ylläpitäjää.

- [ ] `POST /api/v1/org/invite` — omistaja lähettää sähköpostikutsun (token-pohjainen, 48 h voimassa)
- [ ] `POST /api/v1/org/invite/accept` — kutsuttu rekisteröityy ja liittyy organisaatioon automaattisesti
- [ ] `GET /api/v1/org/members` — listaa organisaation jäsenet rooleineen (owner/admin only)
- [ ] `PATCH /api/v1/org/members/{id}/role` — muuta jäsenen rooli (owner only)
- [ ] `DELETE /api/v1/org/members/{id}` — poista jäsen organisaatiosta (owner/admin)
- [ ] Admin-paneeliin "Team"-tab: jäsenlista, roolien muokkaus, kutsu uusia jäseniä

---

### Phase 18 — Frontend-testit & CI/CD-viimeistely

> Tavoite: Myös frontend testataan automaattisesti. Yksikään rikkinäinen commit ei pääse läpi.

- [ ] Vitest + React Testing Library -konfiguraatio (`vitest.config.ts`, `setup.ts`)
- [ ] Yksikkötestit: `ChatWindow`, `MessageBubble` (markdown), `AdminPanel` (tab-navigointi), `Toast`
- [ ] Yksikkötestit `lib/api.ts`: SSE-parsinta, virheenkäsittely, response-validointi
- [ ] Yksikkötestit `lib/admin.ts`: `unwrap<T>`, header-injektio, virhekäsittely
- [ ] E2E-testit (Playwright): login-flow, chat → vastaus renderöityy, session-historia, PDF-upload, widget-näkymä
- [ ] CI-pipeline: frontend-vaihe (`npm ci` → `npm run lint` → `vitest run` → `npm run build`)
- [ ] CI-pipeline: E2E-vaihe (Playwright headless, ajetaan vain `main`-branchissa)
- [ ] Branch protection: `main`-branchiin ei voi pushata ilman vihreää CI-statusta
- [ ] Dependabot-konfiguraatio Python- ja npm-riippuvuuksille

---

### Phase 19 — Tuotannon koventaminen

> Tavoite: Järjestelmä kestää kuorman, toipuu virheistä itse ja on helppo monitoroida.

- [ ] SQLite WAL-moodi (`PRAGMA journal_mode=WAL`) ja `check_same_thread=False` — samanaikaiset kirjoitukset toimivat
- [ ] `GET /api/v1/health` laajennus: tarkistaa SQLite-, ChromaDB- ja LLM-yhteydet; Render käyttää uptime-monitorointiin
- [ ] Retry-logiikka `chain.py`:ään: LLM-kutsujen uudelleenyritys (`RateLimitError`, `APIConnectionError`, max 3 kertaa, exponential backoff)
- [ ] SSE keep-alive: lähetä tyhjä kommenttirivi (`: keepalive\n\n`) 15 s välein — estää Vercel 30 s timeout
- [ ] SSE-virheenkäsittely frontendissä: jos stream katkeaa, näytä virheilmoitus ja "Yritä uudelleen" -painike
- [ ] Graceful degradation: jos ChromaDB ei tavoitettavissa, palauta selkeä 503 eikä 500-stacktrace
- [ ] Redis-pohjainen rate limiting (valinnainen): korvaa in-memory `limiter.py` kun siirrytään multi-instanssi-deployihin
- [ ] Session-invalidointi (`force_logout`) — ks. Phase 15
