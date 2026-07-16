# UFL Crawler — Implementatsiya rejasi (Sonnet uchun)

> Dizayn: [2026-07-16-website-crawler-integration-design.md](superpowers/specs/2026-07-16-website-crawler-integration-design.md)
> Manba: `../website-to-txt-collector/continuous_collector.py` (port qilinadi, ko'chirilmaydi)
> Metod: har vazifa TDD (RED→GREEN→real verifikatsiya→commit). Har faza alohida commit.
> Commit xabari: **Co-Authored-By QATORI YO'Q** (loyiha qoidasi).
> Docker: `"/c/Program Files/Docker/Docker/resources/cli-plugins/docker-compose.exe"` (compose plugin auto-topilmasa).

## Umumiy tamoyillar (har fazada amal qil)
- **Ko'chirma emas, port:** manba kodni o'qib, UFL-uslubida qayta yoz. Manba faylni UFL'ga nusxalama.
- **UFL pipeline'ni qayta ishlat:** `clean/`, `stats/`, `store/` mavjud modullarni chaqir, takrorlama.
- **DI (dependency injection):** MiniMax, tarmoq (WebClient) — testlarga soxta (fake) injektlanadigan qilib yoz. Real tarmoq testlari `@pytest.mark`'siz hermetik bo'lsin (fixture HTML ishlatilsin).
- **Real verifikatsiya:** unit testdan tashqari, har foydalanuvchiga ko'rinadigan qism (CLI/web) real sayt yoki real fixture bilan sinaladi (sessiya darsi: qisqa/sun'iy test yetarli emas).
- **`.gitignore`:** `data/collected/**` qo'shilsin (crawl chiqishi — mualliflik matni, git'ga tushmasin).

---

## FAZA 4.1 — Crawl poydevori (urls, web_client, sitemap)

**Fayllar:** `src/ufl/crawl/__init__.py`, `urls.py`, `web_client.py`, `sitemap.py`
+ `tests/test_crawl_urls.py`, `test_crawl_web_client.py`, `test_crawl_sitemap.py`

**Vazifalar:**
1. `urls.py` — manba 96-181 port qil: `canonical_url` (SSRF: ichki IP/localhost/credential/uzun-URL rad), `host_key`, `belongs_to_site`, `collectable_url` (SKIP_EXTENSIONS), `date_from_url`, `url_hash`, `domain_folder`.
   - **Birlashtir:** `ingest/url.py`dagi mavjud SSRF mantig'ini shu yerga ko'chir, `ingest/url.py` shundan import qilsin (kod takrorlanmasin).
2. `web_client.py` — `WebClient` (xost bo'yicha rate-limit, `request_delay`/`timeout` config'dan), `RobotsPolicy` (robots.txt yuklab, `allowed()`, sitemap havolalarini yig'adi).
3. `sitemap.py` — `parse_sitemap(content)` (gzip-aware, `<loc>`+`<lastmod>`, sitemapindex vs urlset farqlaydi, sanaga ko'ra teskari saralaydi).

**Testlar (RED birinchi):**
- `test_canonical_url_rejects_private_ip`, `..._localhost`, `..._credentials`, `..._strips_tracking_params`, `..._too_long`.
- `test_collectable_url_rejects_binary_extensions`, `..._rejects_other_domain`.
- `test_belongs_to_site_handles_www_and_subdomains`.
- `test_date_from_url_extracts_yyyy_mm_dd`.
- `test_web_client_enforces_delay_between_same_host` (monkeypatch `time`).
- `test_robots_policy_parses_sitemaps_and_disallow` (fixture robots.txt matni).
- `test_parse_sitemap_urlset_and_index`, `..._gzip`, `..._sorts_newest_first` (fixture XML bytes).

**Qabul:** barcha testlar GREEN; `ingest/url.py` yangi `urls.py`dan import qilib, mavjud `test_ingest_url.py` hamon o'tadi.

---

## FAZA 4.2 — Ko'p-strategiyali ekstraksiya (blocks, candidates) + Yaxshilanish A

**Fayllar:** `src/ufl/crawl/blocks.py`, `candidates.py`
+ `tests/test_crawl_blocks.py`, `test_crawl_candidates.py`
+ `ingest/html.py` o'zgartirish (Yaxshilanish A)

**Vazifalar:**
1. `blocks.py` — manba 184-282: `clean_lines`, `fragment_blocks` (BLOCK_TAGS/DROP_TAGS walk), `fragment_text`, `obvious_trash_block`, `clean_content_blocks`.
2. `candidates.py` — manba 313-868: `Candidate` dataclass, `recursive_json_values`, `extract_metadata` (og:title, ld+json datePublished), `candidates_from_page` (JSON-LD articleBody / Nuxt `__NUXT_DATA__` / Next `__NEXT_DATA__` / DOM selektorlar + evristik skorlash: link-density, POSITIVE/NEGATIVE_HINTS, title-word bonus, boilerplate jarima), `dom_candidate`, `probable_article_page`, `simple_selector`, `title_with_punctuation`.
3. **Yaxshilanish A:** `ingest/html.py` `html_to_document` — avval `candidates_from_page` bilan eng kuchli nomzodni ol; bo'sh/juda qisqa bo'lsa trafilatura'ga fallback. `/url` va HTML-fayl ingest avtomatik kuchayadi.

**Testlar:**
- Real fixture HTML saqla: `tests/fixtures/crawl/` — bittadan JSON-LD, Nuxt, Next, sof-DOM sayt sahifasi (kichraytirilgan). Manba: daryo.uz (Nuxt) real ishlagan, kun.uz (DOM). Fixture'larni scratchpad'dan olib, kichraytirib saqla.
- `test_candidates_jsonld_articlebody`, `test_candidates_nuxt_payload`, `test_candidates_next_data`, `test_candidates_dom_scoring_prefers_low_link_density`.
- `test_candidates_boilerplate_penalty` (privacy-policy sahifa past skorlansin).
- `test_clean_content_blocks_removes_ads_and_dups`.
- `test_html_ingest_uses_multistrategy_then_trafilatura_fallback` (Nuxt fixture — trafilatura yolg'iz ushlamaydigan holat).

**Qabul:** GREEN; daryo.uz Nuxt fixture'dan ≥250 belgi toza tana chiqadi; mavjud `test_ingest_html.py` (agar bor) hamon o'tadi.

---

## FAZA 4.3 — Crawl state DB (resumable)

**Fayllar:** `src/ufl/crawl/state.py` + `tests/test_crawl_state.py`

**Vazifalar:** manba 337-603 `State` port — per-domen SQLite: `sitemaps`, `pages`, `adapters`, `ai_batches`, `meta` jadvallar (UFL budget `ufl.db`dan ALOHIDA, `data/collected/<domain>/_state/state.sqlite3`). Metodlar: `add_page` (URL UNIQUE, published normalizatsiya), `next_page` (newest-first), `next_sitemap`, `upsert_sitemap`, `adapter`/`save_adapter`, `counts`, `median_clean_chars`, `_recover_statuses` (processing→discovered restart'da), WAL rejim.

**Testlar:** `test_add_page_dedupes_by_url`, `test_next_page_newest_first`, `test_recover_resets_processing_on_restart`, `test_save_and_read_adapter`, `test_counts_by_status`, `test_median_clean_chars`.

**Qabul:** GREEN; DB tmp_path'da yaratiladi (real `data/`ni ifloslantirmaydi).

---

## FAZA 4.4 — Collector + UFL clean pipeline ulash (LOCAL rejim)

**Fayllar:** `src/ufl/crawl/collector.py`, `categorize.py` + `tests/test_crawl_collector.py`

**Vazifalar:**
1. `collector.py` — manba 1385-1657 `Collector` port, LEKIN nomzod tanlangandan keyin **UFL pipeline chaqiriladi**: har blok → `to_latin` → `is_uzbek` (yo'q bo'lsa tashla) → `assess` → `normalize` → `dedup.check_and_add`. Til-filtridan keyin tana < `min_clean_chars` → `quality_rejected`.
2. `_discover_links`, `process_sitemap`, `process_page`, `refresh_roots`, `run(once, max_steps)`.
3. `categorize.py` — `resolve_category(mode, ...)`: manual → o'zgarmas string; auto → MiniMax (4.7'gacha stub: `web_news` qaytaradi + TODO).
4. WebClient DI: testlar soxta client (fixture HTML qaytaradi) injektlaydi — tarmoqsiz test.

**Testlar:**
- `test_collector_processes_uzbek_article_through_pipeline` (soxta client Nuxt fixture qaytaradi → toza o'zbek matn yoziladi, status done).
- `test_collector_drops_non_uzbek_blocks` (aralash o'zbek+rus fixture → faqat o'zbek qoladi).
- `test_collector_rejects_short_after_language_filter`.
- `test_collector_discovers_links_into_queue`.
- `test_collector_respects_robots_disallow`.

**Qabul:** GREEN; soxta-client bilan to'liq oqim tarmoqsiz test qilinadi.

---

## FAZA 4.5 — Bundled writer + UFL budget hisobi

**Fayllar:** `src/ufl/crawl/writer.py` + `tests/test_crawl_writer.py`

**Vazifalar:** manba 878-1120 `DatasetWriter` port: crash-safe juft chiqish (`.txt` + `.jsonl`), oy-bo'yicha bundling, ~50MiB sharding (config'dan), atomik append (fsync), `recover()` (uzilgan yozuvni rollback), month-range rename. **Qo'shimcha:** har accepted maqola UFL `Store.record_book` (yoki yangi crawl-record) bilan budget'ga qo'shiladi — kategoriya token o'sadi. Token: `stats/tokens.count_tokens` (aniq bo'lsa Gemma, aks holda taxminiy).

**Testlar:** `test_writer_pairs_txt_and_jsonl`, `test_writer_atomic_recover_after_interrupt` (yarim yozuvni simulatsiya → rollback), `test_writer_rolls_shard_at_limit`, `test_writer_records_tokens_to_budget`, `test_writer_never_splits_article_between_shards`.

**Qabul:** GREEN; JSONL formati collector README bilan mos (`id,text,title,date,source_website,source_url`).

---

## FAZA 4.6 — CLI `ufl crawl`

**Fayllar:** `cli.py` o'zgartirish + `tests/test_cli_crawl.py`

**Vazifalar:** `crawl` buyrug'i (`url`, `--category` [8+auto], `--max-articles`, `--once`, `--max-steps`, `--config`), `crawl-status` buyrug'i (state DB'dan counts). Kalit `MINIMAX_API_KEY` env'dan. Category validatsiya (noto'g'ri → xato).

**Testlar:** `test_crawl_cli_local_mode_collects_from_fixture` (soxta client), `test_crawl_cli_rejects_unknown_category`, `test_crawl_status_shows_counts`.

**Qabul:** GREEN + real Docker: `docker compose run --rm ufl ufl crawl https://daryo.uz --category web_news --max-articles 5` → ≥1 toza maqola yig'iladi (daryo Nuxt, local rejim ishlashini sessiyada tasdiqladik).

---

## FAZA 4.7 — MiniMax (ixtiyoriy): kalibratsiya + auto-kategoriya

**Fayllar:** `src/ufl/crawl/minimax.py` + `tests/test_crawl_minimax.py`

> ⚠️ **TOKEN TEJASH MAJBURIY** (foydalanuvchi talabi) — dizayn spec §6.3 to'liq amalga oshirilsin.
> Asosiy tamoyil: MiniMax token maqolalar soniga EMAS, domenlar soniga proporsional bo'lsin.

**Vazifalar:**
1. `MiniMaxClient` — manba 1123-1346 port: `maybe_process` (labellangan bloklar → API →
   candidate/trash/complete validatsiya → **adapter kESH**). Token tejash mexanizmlari MAJBURIY:
   - **Adapter kESH:** kalibratsiya domen uchun ~1 marta; keyin `state.adapter(domain)` bo'lsa
     MiniMax UMUMAN chaqirilmaydi (Collector local ekstraksiya qiladi — bu 4.4'da ulangan).
   - **Belgi-byudjeti:** eng ko'p 6 nomzod, jami ≤180k belgi (manba 1144-1156).
   - **batch_hash dedup:** bir xil payload qayta yuborilmaydi.
   - **Bounded retry:** 429/5xx → backoff, ≤5 urinish; 401/403 → `minimax_blocked` (to'liq to'xtash).
   - `max_completion_tokens=4000`, `temperature=0.1`, `stream=false`. Kalit faqat header'da.
2. **Rol B — auto-kategoriya, LOCAL-BIRINCHI (spec §6.2):**
   - `categorize.py`: `resolve_category` tartibi — (a) URL-yo'l evristikasi (bepul xarita),
     (b) `article:section`/breadcrumb meta (bepul), (c) **domen-standart kESH** (`meta`
     jadval — bir marta aniqlangach qayta ishlatiladi), (d) faqat shundan keyin MiniMax.
   - `classify_category(title, snippet) → category`: faqat **title + ~400 belgi**,
     `max_completion_tokens ≈ 16`, tushuntirishsiz. Noaniq/kalitsiz → `web_news`. Natija
     domen-standart sifatida kESHlanadi.
3. DI: HTTP POST funksiyasi injektlanadi — testlar soxta javob beradi (real API'siz).

**Testlar:** `test_minimax_selects_candidate_and_caches_adapter` (soxta javob),
`test_minimax_rejects_low_confidence`, `test_minimax_rejects_incomplete`,
`test_minimax_401_marks_blocked`, `test_minimax_batch_hash_skips_duplicate`,
`test_category_from_url_path_no_api` (URL-yo'l → API chaqirilmaydi),
`test_category_domain_default_cached_no_api` (2-maqola API'siz),
`test_minimax_classify_only_when_local_signals_absent`,
`test_minimax_classify_falls_back_on_garbage`,
`test_crawl_works_without_key` (kalitsiz — MiniMax butunlay o'tkazib yuboriladi).

**Qabul:** GREEN; kalitsiz crawl 4.4-4.6'dagidek ishlaydi (regressiya yo'q). **Token tejash
tasdig'i:** soxta-API chaqiruvlar sonini sanovchi test — 10 ta bir domen maqolasi uchun
MiniMax kalibratsiya ≤1 marta + kategoriya ≤1 marta chaqirilishini isbotlaydi (har maqola emas).

---

## FAZA 4.8 — Web UI crawl (fon jarayoni)

**Fayllar:** `web/app.py`, `web/templates/crawl.html`, `crawl_status.html` + `tests/test_web_crawl.py`

**Vazifalar:**
- `/crawl` GET — forma (URL, kategoriya dropdown [8 + "Auto (MiniMax)"], max-articles).
- `/crawl/start` POST — **fon jarayoni** (`subprocess` `ufl crawl ...`, web thread'ni bloklamaydi — OCR-muzlash darsi!). Har domen bitta faol crawl.
- `/crawl/status/{domain}` GET — state DB counts + oxirgi maqolalar + meta-refresh.
- `/crawl/stop/{domain}` POST — jarayonga xavfsiz to'xtash.
- Dropdown/option ko'rinishi: mavjud `option{color}` CSS darsini qo'lla (dark-mode).

**Testlar:** `test_crawl_form_renders`, `test_crawl_start_launches_background_and_redirects_to_status` (subprocess mock), `test_crawl_status_reads_state_db`.

**Qabul:** GREEN + **brauzerda real verifikatsiya** (mcp browser): forma → start → status sahifasi progress ko'rsatadi. Web muzlamaydi (fon jarayoni).

---

## FAZA 4.9 — Yaxshilanish B + hujjatlar

**Vazifalar:**
1. **Yaxshilanish B:** `clean/structure.py` yoki `quality.py`ga CMS-boilerplate filtri: `[tahrir]`, `[tahrirlash]`, `[manbasini tahrirlash]`, `[edit]`, `[изменить]` va shu kabi qavs-ichi tahrir-havola qoldiqlari tashlanadi. Test: `test_structure_drops_wiki_edit_markers` (sessiyadagi real Wikipedia artefakti).
2. `docs/DOCKER.md` + `README.md` — crawl bo'limi (CLI, web, VPS detached), **ToS/litsenziya eslatmasi** (§12.4).
3. `config/ufl.toml` `[crawl]`/`[minimax]` seksiyalari, `.env.example`ga `MINIMAX_API_KEY=`.

**Qabul:** GREEN; Wikipedia namunasida `[tahrir...]` endi chiqmaydi.

---

## FAZA 4.10 — VPS deploy

**Vazifalar:**
- `data/collected/**` → `.gitignore`.
- VPS'ga kod yetkaz (tar+scp), image rebuild.
- Detached crawl konteyner namunasi hujjatlashtiriladi: `docker compose run -d --name ufl-crawl-<domain> ufl ufl crawl <url> --category <cat>`.
- Web UI progress sahifasi VPS'da tekshiriladi.
- Bir kichik real crawl (masalan daryo.uz `--max-articles 20`) VPS'da ishga tushirilib, byudjet o'sishi dashboard'da ko'rinishi tasdiqlanadi.

**Qabul:** VPS'da real crawl ≥20 maqola yig'adi, dashboard token o'sishini ko'rsatadi, boshqa saytlar (crm.ibos.uz va h.k.) ta'sirlanmaydi.

---

## FAZA 4.11 — Qo'shimcha kichik UI vazifalari (verifikatsiya kutmoqda)

Bular crawler'dan mustaqil, kichik UX yaxshilanishlari. Ba'zilari **allaqachon kod yozilgan,
lekin brauzerda test qilinmagan va VPS'ga deploy qilinmagan** — implementatsiya fazasida
brauzer-verifikatsiya + deploy qilinadi.

1. **"Hammasini nusxalash" tugmasi (result sahifasi)** — *kod yozilgan, test kutmoqda*.
   `web/templates/result.html`ga `.txt yuklab olish` yoniga "Hammasini nusxalash" (copy-to-clipboard)
   tugmasi qo'shildi. Kichik matnlar uchun foydalanuvchi faylsiz, to'g'ridan-to'g'ri copy-paste
   qilib olishi mumkin. `navigator.clipboard.writeText` + `document.execCommand('copy')` fallback
   (HTTPS ufl.ibos.uz va localhost'da ishlaydi). Bosilганda "✓ Nusxalandi" fikr-bildirgichi,
   bo'sh matnda "Matn bo'sh".
   - **Qoladi:** brauzerda real test (bosish → clipboard'ga tushishi), VPS'ga deploy.
   - **Test g'oyasi:** `test_result_page_has_copy_button` (result.html'da tugma + skript borligini
     tekshiruvchi kichik web test).

*(Foydalanuvchi so'rovi: kichik text bo'lsa fayl o'rniga oddiy copy-paste imkoni.)*

---

## Eslatmalar
- **Hajm:** ~10 faza, katta feature. Har faza mustaqil qiymat beradi va alohida commit qilinadi.
- **MiniMax kalitsiz** har fazada to'liq ishlashi shart (4.7'gacha local rejim to'liq foydali).
- **Regressiya:** har fazadan keyin butun `pytest` to'plami o'tishi kerak (hozir 151 test).
- **Docker Desktop** sessiyada bir necha marta o'chgan — o'chsa qayta ishga tushir (PowerShell `Start-Process`), compose plugin'ni to'g'ridan-to'g'ri path bilan chaqir.
