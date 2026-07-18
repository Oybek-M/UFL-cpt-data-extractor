# UFL — Docker qo'llanmasi (aniq va muammosiz)

> Bu qo'llanma Docker'da tajribasi kam odam uchun yozilgan. **Har bir buyruqni ketma-ket** copy-paste qiling.
> Ikki muhit: **Windows (dev — o'z kompyuteringiz)** va **Contabo VPS (Ubuntu 24.04 — jamoa serveri)**.

---

## 0. Docker nima va nega?

Docker — dasturimizni **barcha kutubxonalari bilan bitta "quti" (image)** ga joylaydi. Shu quti Windows'da ham, serverda ham **bir xil** ishlaydi. Shuning uchun "menda ishladi, sizda ishlamadi" muammosi bo'lmaydi. Python versiyasi, Tesseract, DjVuLibre — hammasi quti ichida, kompyuteringizga alohida o'rnatmaysiz.

- **Image** — o'zgarmas shablon (bizning dastur + kutubxonalar).
- **Container** — image'dan ishga tushgan nusxa (ishlab turgan dastur).
- **Volume** — ma'lumot saqlanadigan papka (host'da qoladi, container o'chsa ham yo'qolmaydi). Bizda `data/` va `models/`.
- **docker compose** — bir nechta sozlamani bitta `docker-compose.yml` fayldan boshqarish.

---

## 1. WINDOWS (dev muhiti)

### 1.1 Docker Desktop o'rnatish (agar yo'q bo'lsa)
1. https://www.docker.com/products/docker-desktop dan **Docker Desktop for Windows** yuklab o'rnating.
2. O'rnatishda **"Use WSL 2 instead of Hyper-V"** belgilangan bo'lsin (tavsiya).
3. Kompyuterni qayta yuklang. Docker Desktop'ni oching, "Engine running" (yashil) bo'lguncha kuting.
4. Tekshirish (PowerShell):
   ```powershell
   docker --version
   docker compose version
   ```
   Ikkalasi versiya chiqarsa — tayyor.

### 1.2 Loyihani ishga tushirish
Loyiha papkasida (PowerShell):
```powershell
cd "C:\Users\Oybek\Documents\Projects programming\StartUps\UFL"

# 1) Image quramiz (birinchi marta 5-15 daqiqa — kutubxonalar yuklanadi)
docker compose build

# 2) Versiyani tekshiramiz
docker compose run --rm ufl ufl version

# 3) data/input ga kitob tashlab, batch ishga tushiramiz
docker compose run --rm ufl ufl run data/input

# 4) Statistika
docker compose run --rm ufl ufl stats
```

> `--rm` = ish tugagach container'ni o'chiradi (tozalik uchun).
> `data/` va `models/` papkalar host'da (Windows'da) qoladi — natijalarni Windows'dan ko'rasiz.

### 1.3 Web UI'ni lokal ochish (Faza 3 tayyor bo'lgach)
```powershell
docker compose up -d web
# Brauzerda: http://localhost:8000
docker compose logs -f web   # loglarni ko'rish
docker compose down          # to'xtatish
```

---

## 2. CONTABO VPS (Ubuntu 24.04) — jamoa serveri

> SSH orqali serverga kiring: `ssh root@SERVER_IP` (yoki o'z foydalanuvchingiz bilan).

### 2.1 Docker Engine o'rnatish (rasmiy usul — eng ishonchli)
Quyidagilarni **ketma-ket** bajaring:

```bash
# Eski/nott'g'ri paketlarni tozalash (bo'lmasa ham zararsiz)
for p in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove -y $p; done

# Docker'ning rasmiy APT repozitoriyasini qo'shish
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker Engine + Compose plugin o'rnatish
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Tekshirish
sudo docker run --rm hello-world
sudo docker compose version
```
`hello-world` "Hello from Docker!" chiqarsa — Docker ishlayapti.

### 2.2 (Ixtiyoriy) sudo'siz ishlatish
```bash
sudo usermod -aG docker $USER
# Chiqib qайта kiring (logout/login) yoki:
newgrp docker
docker run --rm hello-world   # endi sudo'siz
```

### 2.3 Loyihani serverga olib kelish

Repo **private** (GitHub'da) — VPS'dan to'g'ridan-to'g'ri `https://` bilan clone qilib
bo'lmaydi (parol so'raydi). Read-only **deploy key** kerak:

```bash
# 1) VPS'da alohida kalit yaratish (faqat shu repo uchun, faqat o'qish huquqi bilan)
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy_ufl -N "" -C "ufl-vps-deploy-key"
cat /root/.ssh/github_deploy_ufl.pub   # shu chiqishni GitHub'ga qo'shasiz

# 2) GitHub'da: repo → Settings → Deploy keys → Add deploy key → yuqoridagi public key'ni
#    joylashtiring, "Allow write access" BELGILANMASIN (faqat o'qish yetarli)
#    (yoki lokal kompyuterdan: gh repo deploy-key add key.pub --repo <owner>/<repo> --title "VPS")

# 3) SSH host alias sozlash
cat >> /root/.ssh/config <<'EOF'

Host github-ufl
    HostName github.com
    User git
    IdentityFile /root/.ssh/github_deploy_ufl
    IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config

# 4) Clone
sudo apt-get install -y git
cd /var/www
git clone github-ufl:<owner>/<repo>.git ufl
cd /var/www/ufl
```

Shundan keyin yangilash doim oddiy: `git pull && docker compose build && docker compose up -d web`.

### 2.4 Ishga tushirish
```bash
cd /var/www/ufl
cp .env.example .env
nano .env                 # HF_TOKEN kiritish (aniq token hisobi uchun, ixtiyoriy — §5 ga qarang)

docker compose build      # birinchi marta uzoqroq (5-15 daqiqa)
docker compose run --rm ufl ufl version

# (ixtiyoriy) fastText til modeli + Gemma tokenizer yuklab olish — bir marta:
docker compose run --rm ufl python scripts/fetch_models.py

docker compose up -d web  # Web UI'ni fon rejimida, avtomatik qayta ishga tushadi (restart: unless-stopped)
docker compose ps         # ishlab turgan servislar
docker compose logs -f web
```
> `docker-compose.yml`da web porti `127.0.0.1:8000:8000` qilib bog'langan — ya'ni **faqat serverning o'zidan** ko'rinadi, internetdan to'g'ridan-to'g'ri kirib bo'lmaydi. Tashqariga faqat Nginx orqali (§2.5) chiqariladi. Ilovaning o'zida login/parol yo'q (kichik jamoa uchun ataylab shunday) — shuning uchun bu qadam **majburiy**, aks holda 8000-port ochiq qolib ketmaydi.

### 2.5 Firewall (ufw)
```bash
sudo apt-get install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # 80 va 443
sudo ufw enable               # "y" bilan tasdiqlang
sudo ufw status
```
8000-port ochilmaydi — u faqat `127.0.0.1`da, tashqaridan umuman ko'rinmaydi.

### 2.6 Nginx reverse-proxy + Basic Auth + HTTPS
> Ilovada auth yo'qligi sababli, himoyani Nginx darajasida qo'yamiz: **HTTP Basic Auth** (login/parol so'raydi) + **HTTPS**.

```bash
sudo apt-get install -y nginx apache2-utils
# Login/parol yaratish (masalan foydalanuvchi nomi: ufl-team):
sudo htpasswd -c /etc/nginx/.htpasswd ufl-team
# (Yana odam qo'shish uchun -c'siz: sudo htpasswd /etc/nginx/.htpasswd ikkinchi-user)
```

`/etc/nginx/sites-available/ufl` (namuna, `nano` bilan yarating):
```nginx
server {
    listen 80;
    server_name ufl.example.uz;   # o'z domeningiz (yoki server IP)

    auth_basic "UFL — faqat jamoa uchun";
    auth_basic_user_file /etc/nginx/.htpasswd;

    client_max_body_size 200M;    # katta kitob fayllari uchun

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/ufl /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Domen bo'lsa — HTTPS (Let's Encrypt), avtomatik http->https redirect ham qiladi:
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ufl.example.uz
```
> Domeningiz yo'q, faqat IP orqali kirmoqchi bo'lsangiz — HTTPS qadamini o'tkazib yuborsangiz ham bo'ladi (`server_name` o'rniga IP yozing), lekin login/parol brauzerda shifrlanmagan holda ketadi — faqat ishonchli tarmoqda (masalan VPN) ishlating. Imkon qadar domen + HTTPS tavsiya qilinadi.

---

## 3. Kundalik buyruqlar (shpargalka)

| Vazifa | Buyruq |
|---|---|
| Image qurish/yangilash | `docker compose build` |
| Versiya | `docker compose run --rm ufl ufl version` |
| Modellarni yuklash (bir marta, oflayn uchun) | `docker compose run --rm ufl python scripts/fetch_models.py` |
| Batch ishlash | `docker compose run --rm ufl ufl run data/input` |
| Statistika | `docker compose run --rm ufl ufl stats` |
| Web UI fon rejimida | `docker compose up -d web` |
| Loglar | `docker compose logs -f web` |
| To'xtatish | `docker compose down` |
| Kodni yangilash (VPS) | `git pull && docker compose build && docker compose up -d` |
| Ichkariga kirish (debug) | `docker compose run --rm ufl bash` |

---

## 4. Muammolar va yechimlar (troubleshooting)

| Muammo | Sabab / yechim |
|---|---|
| `docker: command not found` | Docker o'rnatilmagan (Windows: Desktop ochilganmi? Ubuntu: §2.1) |
| Windows'da build juda sekin | WSL2 yoqilganini tekshiring; antivirus loyiha papkasini skanerlamasin |
| `permission denied ... docker.sock` (Ubuntu) | §2.2 (usermod) yoki `sudo` bilan ishlating |
| `port 8000 already in use` | Boshqa dastur portni band qilgan → `docker-compose.yml` da portni o'zgartiring (masalan `8001:8000`) |
| `no space left on device` | `docker system prune -a` (keraksiz image/cache tozalash) |
| Tesseract tili yo'q | Image ichida `tesseract --list-langs` → `uzb`,`uzb_cyrl` bo'lishi kerak (Dockerfile'da apt) |
| Tokenizer yuklanmadi | pipeline taxminiy hisobga o'tadi + ogohlantiradi (crash emas). Internet/`.env` HF token tekshiring |
| `data/` bo'sh ko'rinadi | volume to'g'ri ulanganini tekshiring (`docker-compose.yml` `volumes:`) |

---

## 5. Muhim eslatmalar

- **Ma'lumot yo'qolmaydi:** `data/` va `models/` host papkada — container o'chsa ham qoladi.
- **Yangilash oson:** kod o'zgarsa `docker compose build` yetadi, tizimga hech narsa o'rnatmaysiz.
- **Windows ↔ VPS bir xil:** bir xil image, shuning uchun natija bir xil.
- **Xavfsizlik:** Ilovaning o'zida auth yo'q — VPS'da Web UI **doim** Nginx Basic Auth + firewall orqasida bo'lishi shart (§2.5-2.6). 8000-portni hech qachon to'g'ridan-to'g'ri internetga ochmang.
- **Aniq token hisobi:** faqat `scripts/fetch_models.py` ishga tushirilib, Gemma tokenizer yuklab olingandan keyin ishlaydi (gated model — avval HuggingFace'da litsenziyani qabul qilish va `.env`ga `HF_TOKEN` qo'yish kerak). Topilmasa pipeline avtomatik taxminiy (belgi-nisbati) hisobga o'tadi, crash bo'lmaydi.

---

## 6. Saytdan yig'ish (crawl)

Butun sayt/blog/portaldan toza o'zbekcha matnni avtomatik yig'ish (resumable, robots.txt
hurmat qilinadi, newest-first). Dizayn: [2026-07-16-website-crawler-integration-design.md](superpowers/specs/2026-07-16-website-crawler-integration-design.md).

### 6.1 CLI orqali

```bash
# Butun saytni crawl qilish (uzluksiz)
docker compose run --rm ufl ufl crawl https://kun.uz --category web_news

# MiniMax auto-klassifikatsiya (kalit kerak — pastga qarang)
docker compose run --rm ufl ufl crawl https://daryo.uz --category auto

# Sinov uchun cheklab: 5 ta maqoladan keyin to'xtaydi
docker compose run --rm ufl ufl crawl https://kun.uz --category web_news --max-articles 5 --once

# Holatni ko'rish (yig'ilgan/kutayotgan/rad hisobi)
docker compose run --rm ufl ufl crawl-status https://kun.uz
```

### 6.2 Web UI orqali

`http://localhost:8000/crawl` — forma (URL, kategoriya, maksimal maqola soni) →
"Yig'ishni boshlash" fon jarayonini ishga tushiradi (web sahifa muzlamaydi) →
`/crawl/status/{domen}` progress ko'rsatadi (avto-yangilanadi), "To'xtatish" tugmasi bilan
xavfsiz to'xtatiladi (yig'ilgan ma'lumot yo'qolmaydi).

### 6.3 VPS'da uzoq muddatli crawl (detached konteyner)

Uzoq (kunlab) ishlaydigan crawl uchun alohida, mustaqil konteyner tavsiya etiladi —
`web` konteyneriga resurs bo'lishmaydi:

```bash
docker compose run -d --name ufl-crawl-kunuz ufl ufl crawl https://kun.uz --category web_news
docker logs -f ufl-crawl-kunuz          # progress
docker stop ufl-crawl-kunuz              # to'xtatish (xavfsiz — atomik yozuv)
```

Chiqish `data/collected/<domen>/` ostida (`.gitignore`da — git'ga tushmaydi).

### 6.4 MiniMax AI (ixtiyoriy, token-tejamkor)

MiniMax faqat local ekstraksiya ambigu bo'lgan sahifalar uchun ishlatiladi (domen uchun
bir marta kalibrlangach, keyingi barcha sahifalar MiniMax'siz local ishlaydi — token sarfi
maqolalar soniga emas, domenlar soniga proporsional). Kalitsiz crawl to'liq ishlaydi.

Kalitni berish uchun ikki yo'l bor:
1. `.env`ga `MINIMAX_API_KEY=...` qo'shing (docker compose avtomatik o'qiydi).
2. Yoki bo'sh qoldiring — interaktiv terminalda `ufl crawl` ishga tushganda kalitni
   qo'lda kiritishni so'raydi (Enter — faqat local ekstraksiya).

Kalit hech qachon kodga yozilmaydi, logga yoki DB'ga tushmaydi.

### 6.5 Litsenziya / ToS eslatmasi

**Muhim:** crawl faqat sizga huquqiy jihatdan ruxsat etilgan saytlar uchun ishlatilsin.
Har bir sayt uchun avval uning **foydalanish shartlari (ToS)** va **robots.txt**'ini
tekshiring. Collector robots.txt'ni avtomatik hurmat qiladi va odobli so'rov tezligini
(`request_delay`) ta'minlaydi, lekin bu huquqiy javobgarlikni bekor qilmaydi — yig'ilgan
matnни CPT uchun ishlatishdan oldin har doim manba saytning litsenziya/mualliflik-huquqi
shartlarini o'zingiz tasdiqlang.

---

## 7. Fayllardan (eBook/hujjat) data extract qilish

`ufl run` — PDF/DjVu/EPUB/DOCX/PPTX/FB2/HTML/TXT fayllarni avtomatik ekstraksiya qiladi.
Fayllarni kategoriya-papkalarga joylashtirish shart emas — bitta tekis papkaga tashlab
qo'ysangiz ham bo'ladi.

### 7.1 Tekis papka (avto-kategoriya)

```bash
# Har bir fayl mustaqil ravishda qayta ishlanadi, natija fayl-nomi bo'yicha yoziladi
docker compose run --rm ufl ufl run data/input
```

Kategoriya papka nomidan aniqlanadi (masalan `data/input/books/kitob.pdf` → `books`).
Fayl tekis papkada (kategoriya-papkasiz) bo'lsa: avval mahalliy taxmin, keyin (agar
MiniMax kaliti mavjud bo'lsa) fayl nomi+parcha asosida MiniMax kategoriya taklif qiladi,
aks holda standart bo'yicha `books` ga tushadi.

### 7.2 MiniMax orqali struktura tekshiruvi (ixtiyoriy, `--verify-with-minimax`)

Evristika (`clean/structure.py`) aksariyat shovqinni (kolontitul, sahifa raqami,
mundarija, bibliografiya) qat'iy qoidalar bilan olib tashlaydi. Qat'iy chegaradan "bir
pog'ona pastroq" — ya'ni evristika saqlab qolgan, lekin shubhali — bloklar bo'lsa,
`--verify-with-minimax` bayrog'i ularni **bitta hujjat uchun bitta so'rovda** MiniMax'ga
yuboradi:

```bash
docker compose run --rm ufl ufl run data/input --verify-with-minimax
```

Muhim qoidalar:
- MiniMax **matnni hech qachon tahrirlamaydi yoki qayta yozmaydi** — faqat "bu blok
  shovqinmi (tashlash) yoki yo'qmi (qoldirish)" qarorini beradi. CPT matni har doim
  original manbadan olinadi.
- Faqat haqiqatan ham shubhali bloklar bo'lsa chaqiriladi — aniq hujjatlarda (aksariyati)
  MiniMax umuman ishlatilmaydi (token sarfi yo'q).
- Xato/kalit yo'qligi/tarmoq muammosi bo'lsa — **hech narsa qo'shimcha tashlanmaydi**
  (fail-open): evristika natijasi o'zgarishsiz qoladi, dastur hech qachon buzilmaydi.
- Bayroqsiz (standart) `ufl run` MiniMax'ga umuman murojaat qilmaydi.

---

## 8. HuggingFace dataset'lardan yig'ish (`fetch-hf`)

Ba'zi o'zbekcha matn dataset'lari HuggingFace'da allaqachon millionlab qator sifatida
tayyor turibdi (masalan `tahrirchi/uz-books-v2`, `tahrirchi/uz-crawl`, `yakhyo/uz-wiki`).
Bularni qo'lda yuklab olish/o'qish o'rniga, `ufl fetch-hf` streaming rejimda (diskka
to'liq nusxa saqlamasdan) qator-baqator o'qib, mavjud til/sifat/dedup pipeline'idan
o'tkazadi.

### 8.1 Foydalanish

```bash
docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-books-v2 --split lat --category books
docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-crawl --split news --category web_news
docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-crawl --split telegram_blogs --category web_news
docker compose run --rm ufl ufl fetch-hf yakhyo/uz-wiki --split train --category reference
```

- `--limit N` — sinov uchun, faqat N qator (masalan `--limit 100`).
- `--stop-at-budget` — kategoriya budjet-maqsadiga yetgach avtomatik to'xtaydi.
  **Standart: o'chiq** — bayroqsiz dataset oxirigacha (yoki manba tugaguncha) ishlanadi,
  hatto budjetdan oshib ketsa ham (to'xtash-to'xtamaslik qarori foydalanuvchida).
- `--shard-size N` — har shardning qator soni (standart: 1000). Har bir qator "bitta
  blok" sifatida (paragraflarga bo'linmasdan) fastText+transliteratsiya+sifat
  pipeline'idan o'tadi — shuning uchun bitta qatori butun kitob bo'lgan dataset'larda
  (masalan `tahrirchi/uz-books-v2`) 1000 ni juda katta, kichikroq qiymat (masalan `20`)
  qo'yish tavsiya etiladi (kam qatorli, ko'p-hujjatli dataset'larda esa standart yetarli):
  ```bash
  docker compose run --rm ufl ufl fetch-hf tahrirchi/uz-books-v2 --split lat --category books --shard-size 20
  ```

### 8.2 Davom ettirish

Har `dataset-id + split` uchun progress alohida saqlanadi (`data/hf_state/`). Buyruq
uzilib qolsa (tarmoq, vaqt), qayta ishga tushirilganda oxirgi tugallangan shard'dan
davom etadi — boshidan boshlamaydi.

`--shard-size` shu progress fayliga ham yoziladi: birinchi ishga tushirishda berilgan
qiymat saqlanadi va keyingi qayta ishga tushirishlarda (bayroqsiz ham) avtomatik
qayta ishlatiladi — `skip_rows` hisobini buzmaslik uchun. Saqlangan qiymatga zid
`--shard-size` berilsa, buyruq xato bilan to'xtaydi (avval saqlangan qiymatni
ishlatish yoki bayroqni butunlay tashlab qo'yish kerak).

### 8.3 Chiqish

Har shard (standart 1000 qator, yoki `--shard-size` bilan belgilangan qator soni) —
bitta shard fayl: `<output>/<kategoriya>/<dataset-slug>__<split>__shard-NNNNNN.txt`.

### 8.4 Litsenziya eslatmasi

`tahrirchi/*` dataset'lari apache-2.0/mit litsenziyali. `yakhyo/uz-wiki` paketlanishi
mit, lekin tarkib Vikipediya matni (CC BY-SA) — foydalanishdan oldin o'z loyihangiz
uchun litsenziya mosligini tekshiring (§6.5'dagi kabi umumiy eslatma shu yerga ham
tegishli).

---

## 9. ziyouz.com Kutubxonasidan ommaviy yig'ish (fetch-ziyouz)

"Kutubxona" bo'limidagi (~13,000 fayl, 42 kategoriya) barcha PDF/EPUB/DOC/FB2/DJVU/TXT
faylni avtomatik topib, mavjud tozalash pipeline'i orqali o'tkazadi. Dizayn:
[2026-07-18-ziyouz-bulk-downloader-design.md](superpowers/specs/2026-07-18-ziyouz-bulk-downloader-design.md).

### 9.1 Ishlatish

```bash
# Butun kutubxonani yig'ish (uzluksiz, davomiy)
docker compose run --rm ufl ufl fetch-ziyouz

# Sinov uchun: 5 ta elementdan keyin to'xtaydi
docker compose run --rm ufl ufl fetch-ziyouz --limit 5

# Faqat bitta UFL kategoriyasi
docker compose run --rm ufl ufl fetch-ziyouz --category books
```

### 9.2 Davomiylik va litsenziya

Har bir element `ufl.db`da `ziyouz:<id>` kaliti bilan qayd etiladi — to'xtatib qayta
ishga tushirilsa, allaqachon qayta ishlangan elementlar qayta yuklab olinmaydi.
Kutubxona sahifalari (pagination) esa har safar qaytadan yuriladi (arzon — bir necha
yuz sahifa), faqat qimmat qism (yuklab olish+qayta ishlash) qayta bajarilmaydi.

Audio (mp3) va boshqa matn-bo'lmagan fayllar kengaytma bo'yicha avtomatik o'tkazib
yuboriladi. Xaritada yo'q (yangi paydo bo'lgan) kategoriya nomi ogohlantirish bilan
o'tkazib yuboriladi — `src/ufl/ziyouz/category_map.py`ga qo'shish mumkin.

> **Litsenziya:** sayt "faqat shaxsiy mutolaa, tijoriy foydalanish taqiqlanadi" deydi —
> hozirgi bosqich uchun (tijoriy bo'lmagan MVP tayyorgarlik) qabul qilingan qaror,
> tijoriylashuvdan oldin qayta ko'rib chiqiladi (spec §"Litsenziya eslatmasi"ga qarang).

## 10. Korpusni yakunlash (finalize-corpus)

Yig'ilgan korpusni (`UFL-Datas`) jamoaning umumiy training bazasiga topshirishdan oldin
ishga tushiriladi. Uch bosqich: global (korpus-bo'ylab) dedup, PII (email/telefon)
tozalash, HF dataset manbasini fayl nomidan yashirish. Dizayn:
[2026-07-18-finalize-corpus-design.md](superpowers/specs/2026-07-18-finalize-corpus-design.md).

### 10.1 Ishlatish

**Avval hisobot ko'rish uchun (hech narsa o'zgarmaydi):**

```bash
docker compose run --rm ufl ufl finalize-corpus
```

**Haqiqiy o'zgarish qilish uchun:**

```bash
docker compose run --rm ufl ufl finalize-corpus --apply
```

### 10.2 Bosqichlar va xavfsizlik

Bosqich tartibi qat'iy: **dedup → PII → HF nomini yashirish**. Rename doim oxirida
ishlaydi, chunki dedup va PII bosqichlari HF fayllarni asl (dataset_slug asosidagi)
nomi orqali aniqlaydi.

Dublikat fayllar **o'chirilmaydi** — `data/rejected/duplicates/{category}/`ga
ko'chiriladi (repo ichida, gitignored, kerak bo'lsa qaytarib olish mumkin).

Yangi HF dataset qo'shilganda (masalan yangi `tahrirchi/...` yoki boshqa manba), uni
`src/ufl/finalize/hf_rename.py`dagi `DATASET_ALIAS` xaritasiga qo'shish kerak — aks holda
o'sha dataset fayllari "Noma'lum dataset" deb ogohlantiriladi va qayta nomlanmaydi
(xavfsizlik uchun — hech qachon taxminiy alias yaratilmaydi).
