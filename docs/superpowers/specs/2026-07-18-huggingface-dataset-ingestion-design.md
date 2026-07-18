# HuggingFace dataset ingestion (`ufl fetch-hf`) — dizayn

## Maqsad

Loyihaning CPT token budjetini (1.2B) eng tez va eng arzon yo'l bilan to'ldirish uchun,
HuggingFace'da allaqachon mavjud, sifatli o'zbekcha matn dataset'laridan foydalanish.
Bitta faylni qo'lda yuklab/o'qishdan farqli o'laroq, bu dataset'lar millionlab
qator/hujjatni bitta joyda taqdim etadi.

## Qamrov (bu bosqichda)

Uch dataset qabul qilinadi (foydalanuvchi tanlovi bo'yicha, real ko'rib chiqilgan):

| Dataset | Split | Kategoriya | Hajmi |
|---|---|---|---|
| `tahrirchi/uz-books-v2` | `lat` | `books` | ~40k kitob |
| `tahrirchi/uz-crawl` | `news` | `web_news` | ~1.25M qator |
| `tahrirchi/uz-crawl` | `telegram_blogs` | `web_news` | ~368k qator |
| `yakhyo/uz-wiki` | `train` | `reference` | ~300k maqola |

**Ataylab tashlab qo'yilgan** (foydalanuvchi bilan kelishilgan):
- `murodbek/uz-books` — `tahrirchi/uz-books-v2`ning eskiroq (Tesseract OCR) nusxasi;
  bir xil ~40k kitob, ikkalasini ham olish budjetni soxta ikki barobar oshiradi.
- `tahrirchi/uzlib` — format mos emas (til-test/quiz: savol+4 variant+javob, prose emas).
- `nickoo004/uzbekdata` — sifatsiz (kichik, sintetik, takrorlanuvchi marketing-javoblar).

Kelajakda yangi dataset qo'shish — shunchaki yangi qator (`--dataset-id`, `--split`,
`--category`, `--text-column`) CLI orqali, kod o'zgarishisiz.

## Muhim texnik cheklov: STREAMING SHART

Lokal Windows diskda atigi ~24GB bo'sh joy bor; `uz-books-v2`ning o'zi xom holda 24GB.
**Hech qachon** `datasets` kutubxonasining oddiy (to'liq yuklab oluvchi) rejimi
ishlatilmaydi — faqat `load_dataset(..., streaming=True)`, bu qator-baqator internetdan
o'qiydi, diskka to'liq nusxa saqlamaydi.

## CLI

```bash
ufl fetch-hf <dataset-id> --split <split> --category <category> [--text-column text]
             [--limit N] [--stop-at-budget] [--config config/ufl.toml]
```

- `--text-column` — standart `"text"` (barcha 3 dataset shu nomni ishlatadi).
- `--limit N` — ixtiyoriy, sinov uchun (masalan `--limit 100`).
- `--stop-at-budget` — **standart: OCHIQ EMAS**. Foydalanuvchi aniq talab qildi: to'xtash
  qarorini o'zi berishi kerak. Bayroq berilmasa, dataset oxirigacha (yoki manba tugaguncha)
  ishlanadi — ortiqcha ishlashi mumkin, bu qabul qilingan. Bayroq berilsa, kategoriya
  budjet-maqsadiga yetgach avtomatik to'xtaydi.

## Oqim (har qator uchun)

OCR/struktura-tozalash bosqichlari **yo'q** (manba allaqachon ekstrakt qilingan matn,
skanerlangan kitob emas). Har qator quyidan o'tadi:

```
HF qator (matn) -> til-aniqlash -> sifat-filtri -> normalize (translit) -> dedup -> yozish
```

`clean/apply.py`dagi mavjud `clean_paragraphs()` funksiyasi qayta ishlatiladi (bir xil
mantiq — endi bitta hujjat blok-ro'yxati o'rniga, HF-qatorlar oqimi beriladi).

## Chiqish: shard fayllar

Million qatorni birma-bir faylga yozish o'rniga, har **1000 qator** (standart, sozlanadi
emas — YAGNI) bitta shard faylga yig'iladi:

```
<output>/<category>/<dataset-slug>__<split>__shard-000001.txt
<output>/<category>/<dataset-slug>__<split>__shard-000002.txt
...
```

`dataset-slug` — `/` -> `_` (masalan `tahrirchi_uz-crawl`). Har shard uchun mavjud
`write_output()` bilan bir xil pattern: `.txt` (toza matn), `reports/*.json` (shard
statistikasi), kerak bo'lsa `rejected/*.jsonl`.

## Davom ettirish (resumability)

Million+ qatorli dataset'ni bitta seansda oxirigacha ishlash amaliy emas (uzilishi
mumkin — tarmoq, vaqt). Har `dataset-id + split` uchun progress holati saqlanadi:

- Yangi kichik SQLite fayl (`data/hf_state/<dataset-slug>__<split>.sqlite3`): oxirgi
  tugallangan shard raqami (`last_completed_shard`).
- Qayta ishga tushirilganda, `last_completed_shard * 1000` qator sonini
  `dataset.skip(N)` (datasets kutubxonasining o'zi qo'llab-quvvatlaydi) orqali
  qoldirib, davom etadi — boshidan boshlamaydi.
- Har shard **muvaffaqiyatli yozilgandan keyingina** progress yangilanadi (atomik —
  yarim yozilgan shard hisoblanmaydi).

## Budjet hisobga olish

Har shard — `Store.record_book()` orqali bitta yozuv (`path = "hf:<dataset>:<split>:shard-NNNNNN"`),
mavjud `exact_tokens`/`estimated_tokens` maydonlari bilan — hozirgi budjet-hisoblash
tizimi (409-summasi to'g'ridan-to'g'ri ishlaydi, kod o'zgarishisiz).

## Lokal chiqish joyi: `UFL-Datas`

Foydalanuvchi tasdiqladi: **barcha** pipeline natijasi (`ufl run`, `ufl crawl`,
`ufl fetch-hf`) endi `C:\Users\Oybek\...\StartUps\UFL-Datas\<kategoriya>\...` ga
yozilishi kerak (repo ichidagi `data/output/` o'rniga), kategoriya-papkalar bilan.

**Yechim — faqat Docker Compose darajasida, kod/config o'zgarishisiz:**
`docker-compose.override.yml` (gitignored, faqat Windows lokal muhitda mavjud) qo'shiladi:

```yaml
services:
  ufl:
    volumes:
      - "../UFL-Datas:/app/data/output"
  web:
    volumes:
      - "../UFL-Datas:/app/data/output"
```

Bu — `/app/data/output` yo'lini (config'dagi `paths.output` shunga mos keladi) shu
tashqi papkaga almashtiradi, **faqat** lokal Windows muhitida (fayl gitignored, VPS'da
umuman yo'q — VPS o'z holicha `data/output/` bilan davom etadi). Hech qanday Python kod
yoki `config/ufl.toml` o'zgarmaydi.

## Yangi bog'liqlik

`requirements.txt`ga `datasets` (HuggingFace) qo'shiladi — streaming yuklash uchun.
Versiya `huggingface-hub==1.24.0` bilan mos kelishi build vaqtida tekshiriladi.

## Litsenziya eslatmasi

`tahrirchi/*` — apache-2.0/mit. `yakhyo/uz-wiki` — mit (paketlash), lekin tarkib
Vikipediya matni (CC BY-SA) — mavjud crawl-litsenziya eslatmasi (`docs/DOCKER.md` §6.5)
kabi, bu ham hujjatlashtiriladi.
