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
```bash
# Agar git bo'lsa:
sudo apt-get install -y git
cd /var/www
git clone <REPO_URL> ufl   # yoki repo hali yo'q bo'lsa — scp bilan yuklang
cd /var/www/ufl
```
> Repo hali GitHub'da bo'lmasa: Windows'dan `scp -r` bilan yoki `rsync` bilan yuklaysiz. (Sizga alohida ko'rsataman.)

### 2.4 Ishga tushirish
```bash
cd /var/www/ufl
cp .env.example .env      # sozlamalar (parol va h.k.) — .env ni tahrirlang
docker compose build      # birinchi marta uzoqroq
docker compose run --rm ufl ufl version
docker compose up -d web  # Web UI'ni fon rejimida
docker compose ps         # ishlab turgan servislar
docker compose logs -f web
```

### 2.5 Nginx reverse-proxy + HTTPS (Web UI'ni tashqariga chiqarish)
> Contabo'da odатда Nginx bor. Web UI faqat `127.0.0.1:8000` da tinglaydi, tashqariga Nginx orqali chiqadi (xavfsizroq).

`/etc/nginx/sites-available/ufl` (namuna):
```nginx
server {
    server_name ufl.example.uz;   # o'z domeningiz
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/ufl /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# HTTPS (Let's Encrypt):
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ufl.example.uz
```
> **Privacy:** Web UI **parol** bilan himoyalangan (`.env` da), va Nginx'da IP allowlist ham qo'shsa bo'ladi.

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
- **Xavfsizlik:** VPS'da Web UI'ni **doim parol/HTTPS** orqasida saqlang (privacy — loyihamizning asosiy qadriyati).
