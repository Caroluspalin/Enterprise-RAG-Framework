# Project State

Paivitetty: 2026-04-06

## Viimeksi tehty

- `test_ingest.py` (28 testiä): compute_file_hash, find_pdfs (rekursiivinen, reunatapaukset), load_and_split (oikea PDF + oikea RecursiveCharacterTextSplitter, chunk_size, overlap, metadata), get_already_ingested_hashes, ingest() full integration (deduplikaatio, --reset, tyhja kansio, ei-PDF, metadata, page 1-indeksointi, chunk ID -muoto, muuttuneen tiedoston uudelleensyotto)
- `test_chain.py` (13 testiä): prompt-template, LLM-backend-valinta, invoke_chain, format_sources, build_chain
- `test_chat_stream.py` (13 testiä): SSE-striimaus, session-persistointi, widget auth
- Kokonaiskattavuus 82 % (chain 100 %, db 97 %, ingest 92 %, logger 100 %, api 68 %)
- Yhteensa 104 testiä, kaikki vihrealla

## Tunnetut ongelmat / Keskeneraiset asiat

- INTERNAL_ADMIN_SECRET puuttuu Renderista ja Vercelista — admin-paneeli ei toimi tuotannossa
- `widget.js` ei viela testattu ulkoisella sivustolla tuotannossa
- `src/retriever.py` coverage 63 % — yksikkotestit puuttuvat
- `api.py` coverage 68 % — upload-, documents-, delete-endpointit testaamatta
- CI/CD-pipeline (GitHub Actions) puuttuu
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

Phase 10: GitHub Actions CI/CD -pipelinen luominen testien ja tietoturvalinterin (Bandit/Snyk) automaattista ajoa varten.
