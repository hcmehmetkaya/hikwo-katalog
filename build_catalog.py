"""Hikwo PDF katalog üretici.

hikwo.com kategori sayfalarını okur, ürün görsellerini indirir ve
fotoğraflı bir PDF katalog (site/katalog.pdf) ile indirme sayfası (site/index.html) üretir.
GitHub Actions her gün çalıştırır; elle çalıştırmak için:  python build_catalog.py
Test için:  python build_catalog.py --sample sample.json
"""
import argparse, base64, html, io, json, math, os, re, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).parent
OUT = ROOT / "site"
CACHE = ROOT / ".img-cache"
SITE = "https://www.hikwo.com"
TR_TZ = timezone(timedelta(hours=3))

# ---- Katalog ayarları (değiştirmek istersen burası) ----
CATEGORY = os.environ.get("KATEGORI", "silikon-kalip")
TITLE = os.environ.get("KATALOG_BASLIK", "Silikon Kalıp Kataloğu")

SECTIONS = [  # (bölüm adı, kısa açıklama, anahtar kelimeler) — ürün ilk eşleşen bölüme girer
    ("Vazo Kalıpları", "Pampas, tombul, minyatür ve özel tasarım vazolar", r"vazo"),
    ("Mumluk & Tealight", "Tealight, kapaklı mumluk ve şamdan kalıpları", r"mumluk|tealight|şamdan|mum kalıb"),
    ("Tepsi & Tabak", "Sunum tepsileri, takı tabakları ve dresuar tepsileri", r"tepsi|tabak|tabağı|karo"),
    ("Boyama & Etkinlik", "Çocuk etkinlikleri ve boyama setleri", r"boyama|etkinlik"),
    ("Saksı & Kalemlik", "Sukulent saksıları ve kalemlikler", r"saksı|kalemlik|sukulent"),
    ("Kutu, Kase & Organizer", "Saklama kutuları, kaseler ve şekerlikler", r"kutu|kase|şekerlik|organizer|peçetelik"),
    ("Tütsülük & Küllük", "Şömine tütsülükler ve küllükler", r"tütsülük|küllük|şömine"),
    ("Biblo & Figür", "Biblolar, büstler ve dekoratif objeler", r"biblo|figür|büst|obje|heykel|rölyef|tablo"),
]
OTHER = ("Diğer Ürünler", "Kategorideki diğer kalıplar ve yardımcı ürünler")

PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:TL|₺)")


def tl(s):
    return float(s.replace(".", "").replace(",", "."))


def fmt_tl(n):
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " TL"


# ------------------------------------------------------------------ scraping
def get(session, url, tries=4):
    for i in range(tries):
        try:
            r = session.get(url, timeout=40)
            if r.status_code == 200:
                return r
            print(f"  {url} -> HTTP {r.status_code}", file=sys.stderr)
        except Exception as e:  # noqa
            print(f"  {url} -> {e}", file=sys.stderr)
        time.sleep(2 + 3 * i)
    return None


def sig_of(el):
    parts = []
    while el is not None and getattr(el, "name", None) not in (None, "body", "[document]"):
        parts.append(el.name + "." + ".".join(sorted(el.get("class", []))))
        el = el.parent
    return "<".join(parts)


def img_of(card):
    im = card.find("img")
    if not im:
        return ""
    for attr in ("data-src", "data-original", "data-lazy", "data-srcset", "srcset", "src"):
        v = (im.get(attr) or "").strip().split(" ")[0].split(",")[0]
        if v and not v.startswith("data:") and not re.search(r"blank|placeholder|loading", v, re.I):
            return urljoin(SITE, v)
    return ""


def extract(soup, want_sig=None):
    """Sayfadaki asıl ürün ızgarasını bulur (sponsor/popüler bölümleri hariç)."""
    groups = {}
    for a in soup.select('a[href*="/urun/"]'):
        href = urlparse(urljoin(SITE, a["href"])).path
        child, parent = a, a.parent
        while parent is not None and parent.name not in ("body", "[document]"):
            g = groups.setdefault(id(parent), (parent, {}))[1]
            g.setdefault(id(child), (child, set()))[1].add(href)
            child, parent = parent, parent.parent
    best, best_n, best_sig = None, 0, ""
    for parent, kids in groups.values():
        n = sum(1 for _, s in kids.values() if len(s) == 1)
        sig = sig_of(parent)
        if want_sig and sig == want_sig and n:
            best, best_sig = kids, sig
            break
        if n > best_n:
            best, best_n, best_sig = kids, n, sig
    items = []
    for card, hrefs in (best or {}).values():
        if len(hrefs) != 1:
            continue
        href = next(iter(hrefs))
        names = [(a.get("title") or a.get_text(" ", strip=True)) for a in card.select('a[href*="/urun/"]')]
        names = [n for n in names if n and not re.search(r"TL|sepet", n, re.I)]
        name = max(names, key=len) if names else ((card.find("img") or {}).get("alt") or "")
        prices = [tl(p) for p in PRICE_RE.findall(card.get_text(" ", strip=True))]
        prices = [p for p in prices if p > 0]
        if not name or not prices:
            continue
        img = img_of(card)
        m = re.search(r"products/(\d+)/", img)
        items.append({
            "name": re.sub(r"\s+", " ", name).strip(),
            "url": SITE + href,
            "img": img,
            "price": min(prices),
            "old": max(prices) if max(prices) > min(prices) else None,
            "pid": int(m.group(1)) if m else 0,
        })
    return items, best_sig


def scrape():
    import requests
    from bs4 import BeautifulSoup
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (HikwoKatalog/1.0; +https://www.hikwo.com)"
    base = f"{SITE}/kategori/{CATEGORY}"
    r = get(s, base)
    if not r:
        raise SystemExit("Kategori sayfası okunamadı")
    soup = BeautifulSoup(r.text, "html.parser")
    first, sig = extract(soup)
    pages = 1
    for a in soup.select('a[href*="tp="]'):
        m = re.search(r"[?&]tp=(\d+)", a["href"])
        if m:
            pages = max(pages, int(m.group(1)))
    tot = re.search(r"Toplam\s+([\d.]+)\s+ürün", soup.get_text(" "), re.I)
    total = int(tot.group(1).replace(".", "")) if tot else None
    if total and first:
        pages = max(pages, math.ceil(total / len(first)))
    print(f"İlk sayfa: {len(first)} ürün, {pages} sayfa, sitede toplam: {total}")
    seen = {p["url"]: p for p in first}
    for n in range(2, pages + 1):
        time.sleep(1.5)
        rr = get(s, f"{base}?tp={n}")
        if not rr:
            continue
        items, _ = extract(BeautifulSoup(rr.text, "html.parser"), sig)
        new = [p for p in items if p["url"] not in seen]
        print(f"  sayfa {n}: {len(items)} ürün, {len(new)} yeni")
        for p in new:
            seen[p["url"]] = p
    products = list(seen.values())
    for p in products:
        p["imgdata"] = fetch_image(s, p["img"])
    return products, total


def fetch_image(s, url):
    """Görseli indirir (varsa büyük sürümü), 700px JPEG'e küçültür, data URI döner."""
    if not url:
        return ""
    from PIL import Image
    CACHE.mkdir(exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", urlparse(url).path.lower())[-120:] + ".jpg"
    fp = CACHE / key
    if not fp.exists():
        raw = None
        for cand in (url.split("?")[0].replace("_min.", "."), url):
            try:
                r = s.get(cand, timeout=40)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                    raw = r.content
                    break
            except Exception:  # noqa
                pass
        if not raw:
            return ""
        try:
            im = Image.open(io.BytesIO(raw))
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            im = im.convert("RGB")
            im.thumbnail((700, 700))
            im.save(fp, "JPEG", quality=82, optimize=True, progressive=True)
        except Exception as e:  # noqa
            print(f"  görsel açılamadı {url}: {e}", file=sys.stderr)
            return ""
    return "data:image/jpeg;base64," + base64.b64encode(fp.read_bytes()).decode()


# ------------------------------------------------------------------ rendering
def code_of(name):
    m = re.search(r"\b([A-Z]{1,2}\d{3,7})\b\s*$", name)
    return m.group(1) if m else ""


def clean_name(name):
    n = re.sub(r"\s*[-–/]?\s*\b[A-Z]{1,2}\d{3,7}\b\s*$", "", name)
    n = re.sub(r"\s*[-–]\s*Taş To\w* Kal\w*\s*$", "", n, flags=re.I)
    return n.strip(" -–") or name


def group(products):
    secs = [(t, d, re.compile(rx, re.I), []) for t, d, rx in SECTIONS]
    other = []
    for p in products:
        for t, d, rx, lst in secs:
            if rx.search(p["name"]):
                lst.append(p)
                break
        else:
            other.append(p)
    out = [(t, d, lst) for t, d, _, lst in secs if lst]
    if other:
        out.append((*OTHER, other))
    for _, _, lst in out:
        lst.sort(key=lambda p: -p["pid"])
    return out


def card(p):
    e = html.escape
    off = round((1 - p["price"] / p["old"]) * 100) if p.get("old") else 0
    img = f'<img src="{p["imgdata"]}" alt="">' if p.get("imgdata") else '<div class="noimg">hikwo</div>'
    code = code_of(p["name"])
    return f'''<a class="card" href="{e(p["url"])}">
  <div class="ph">{img}{f'<span class="off">%{off}</span>' if off >= 5 else ''}</div>
  <div class="tx"><div class="nm">{e(clean_name(p["name"]))}</div>
  <div class="pr"><span class="now">{fmt_tl(p["price"])}</span>{f'<span class="old">{fmt_tl(p["old"])}</span>' if p.get("old") else ''}</div>
  {f'<div class="cd">Ürün kodu {e(code)}</div>' if code else ''}</div></a>'''


def build_html(products, now):
    e = html.escape
    secs = group(products)
    date = f"{now.day} {['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'][now.month-1]} {now.year}"
    disc = [1 - p["price"] / p["old"] for p in products if p.get("old")]
    max_off = round(max(disc) * 100) if disc else 0
    cheapest = min(p["price"] for p in products)
    newest = sorted(products, key=lambda p: -p["pid"])
    pics = [x for x in newest if x.get("imgdata")] or [{"imgdata": ""}]
    wall, k = "", 0
    for c in range(4):
        for r in range(4):
            p = pics[k % len(pics)]; k += 1
            top = r * 77 + (34 if c % 2 else 0)
            img = f'<img src="{p["imgdata"]}" alt="">' if p["imgdata"] else ""
            wall += f'<div class="w" style="left:{c*61+10}mm;top:{top}mm">{img}</div>'
    t_words = TITLE.split()
    t_main, t_last = " ".join(t_words[:-1]), t_words[-1]
    toc = "".join(f'<a class="toc-row" href="#s{i}"><span class="toc-p" data-t="#s{i}"></span><span class="toc-c">{len(l)} ürün</span><span class="toc-n">{e(t)}</span></a>'
                  for i, (t, _, l) in enumerate(secs))
    new_cards = "".join(card(p) for p in newest[:9])
    body = ""
    for i, (t, d, lst) in enumerate(secs):
        body += f'''<section class="sec" id="s{i}" data-title="{e(t)}">
<header class="sh"><div class="sn">{i+1:02d}</div><div><h2>{e(t)}</h2><p>{e(d)} · {len(lst)} ürün</p></div></header>
<div class="grid">{"".join(card(p) for p in lst)}</div></section>'''
    fonts = (ROOT / "fonts").resolve().as_uri()
    return f'''<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>Hikwo {e(TITLE)}</title><style>
@font-face{{font-family:IL;src:url({fonts}/inter-latin-400-normal.woff);font-weight:400}}
@font-face{{font-family:IL;src:url({fonts}/inter-latin-500-normal.woff);font-weight:500}}
@font-face{{font-family:IL;src:url({fonts}/inter-latin-600-normal.woff);font-weight:600}}
@font-face{{font-family:IX;src:url({fonts}/inter-latin-ext-400-normal.woff);font-weight:400}}
@font-face{{font-family:IX;src:url({fonts}/inter-latin-ext-500-normal.woff);font-weight:500}}
@font-face{{font-family:IX;src:url({fonts}/inter-latin-ext-600-normal.woff);font-weight:600}}
@font-face{{font-family:FL;src:url({fonts}/fraunces-latin-600-normal.woff);font-weight:600}}
@font-face{{font-family:FX;src:url({fonts}/fraunces-latin-ext-600-normal.woff);font-weight:600}}
@font-face{{font-family:FL;src:url({fonts}/fraunces-latin-700-normal.woff);font-weight:700}}
@font-face{{font-family:FX;src:url({fonts}/fraunces-latin-ext-700-normal.woff);font-weight:700}}
@font-face{{font-family:FL;src:url({fonts}/fraunces-latin-500-italic.woff);font-weight:500;font-style:italic}}
@font-face{{font-family:FX;src:url({fonts}/fraunces-latin-ext-500-italic.woff);font-weight:500;font-style:italic}}
:root{{--ink:#1d1b18;--stone:#f3efe8;--sand:#e4ddd1;--mute:#6e685f;--acc:#0e5a57;--sale:#b6412a}}
@page{{size:A4;margin:16mm 13mm 18mm;
  @bottom-left{{content:"hikwo.com · {e(TITLE)}";font:500 7.5pt IL,IX,sans-serif;color:#8a8379}}
  @bottom-right{{content:counter(page);font:600 8pt IL,IX,sans-serif;color:#1d1b18}}
  @top-right{{content:string(sec);font:500 7.5pt IL,IX,sans-serif;color:#8a8379}}}}
@page cover{{margin:0;@bottom-left{{content:none}}@bottom-right{{content:none}}@top-right{{content:none}}}}
@page back{{margin:0;@bottom-left{{content:none}}@bottom-right{{content:none}}@top-right{{content:none}}}}
*{{box-sizing:border-box}}
body{{margin:0;font:400 9pt/1.4 IL,IX,sans-serif;color:var(--ink)}}
a{{color:inherit;text-decoration:none}}
h1,h2,.serif{{font-family:FL,FX,serif;font-weight:600}}
.cover{{page:cover;height:297mm;background:#141210;color:#fff;position:relative;overflow:hidden}}
.wall{{position:absolute;left:-26mm;top:-58mm;width:262mm;height:250mm;transform:rotate(-9deg)}}
.w{{position:absolute;width:56mm;height:72mm;border-radius:5mm;overflow:hidden;background:#2a2621}}
.w img{{width:100%;height:100%;object-fit:cover;display:block}}
.fade{{position:absolute;left:0;right:0;top:0;height:297mm;background:linear-gradient(180deg,rgba(20,18,16,.8) 0%,rgba(20,18,16,0) 13%,rgba(20,18,16,0) 32%,rgba(20,18,16,.88) 46%,#141210 58%)}}
.topbar{{position:absolute;top:13mm;left:16mm;right:16mm;height:9mm}}
.brand{{font:600 10.5pt IL,IX,sans-serif;letter-spacing:.34em;color:#fff;margin:0;position:absolute;left:0;top:2mm}}
.pill{{position:absolute;right:0;top:0;font:500 8.5pt IL,IX,sans-serif;color:#e8e2d8;background:rgba(20,18,16,.72);border:.3mm solid rgba(255,255,255,.22);border-radius:6mm;padding:2mm 4.5mm 2mm 3.5mm}}
.pill i{{display:inline-block;width:2.2mm;height:2.2mm;border-radius:50%;background:#5fd0c4;margin-right:2mm;vertical-align:.2mm}}
.ct{{position:absolute;left:16mm;right:16mm;top:166mm}}
.cover h1{{font:700 52pt/0.98 FL,FX,serif;margin:0 0 6mm;color:#fff;letter-spacing:-.5pt}}
.cover h1 em{{display:block;font-style:italic;font-weight:500;color:#5fd0c4}}
.lead{{font-size:12pt;line-height:1.5;color:#cfc7ba;margin:0;max-width:128mm}}
.facts{{position:absolute;left:16mm;right:16mm;bottom:17mm;display:flex;border-top:.3mm solid #3c3832;padding-top:6mm}}
.f{{flex:1}}.f b{{display:block;font:700 22pt/1.05 FL,FX,serif;color:#fff}}.f span{{font-size:8.5pt;color:#a59d90}}
.f.hl b{{color:#5fd0c4}}
.intro{{page-break-before:always}}
.intro h2{{font-size:26pt;margin:0 0 3mm}}
.intro .sub{{color:var(--mute);margin:0 0 8mm;font-size:10pt}}
.toc-row{{display:block;padding:3.2mm 0;border-bottom:.25mm solid var(--sand);font-size:11pt}}
.toc-n{{font-weight:600}}.toc-c{{float:right;color:var(--mute);margin-right:4mm;font-size:9pt;width:20mm;text-align:right}}
.toc-p{{float:right;width:10mm;text-align:right;font-weight:600;color:var(--acc)}}.toc-p::after{{content:target-counter(attr(data-t),page)}}
.how{{margin-top:9mm;background:var(--stone);border-radius:3mm;padding:6mm 7mm;display:flex;gap:7mm}}
.how div{{flex:1}}.how b{{display:block;font-size:10pt;margin-bottom:1mm}}.how span{{color:var(--mute);font-size:8.5pt}}
.newh{{margin:10mm 0 4mm;font-size:15pt}}
.sec{{page-break-before:always}}
.sh{{display:flex;align-items:center;gap:5mm;margin:0 0 5mm;padding-bottom:3mm;border-bottom:.6mm solid var(--ink)}}
.sh h2{{font-size:22pt;margin:0;line-height:1.05;string-set:sec content()}}
.sh p{{margin:1mm 0 0;color:var(--mute);font-size:9pt}}
.sn{{font:600 30pt FL,FX,serif;color:var(--acc);line-height:1}}
.grid{{margin:0 -2mm;font-size:0}}
.card{{display:inline-block;vertical-align:top;font-size:9pt;width:33.333%;padding:0 2mm 3.5mm;break-inside:avoid;page-break-inside:avoid}}
.ph{{position:relative;height:50mm;background:var(--stone);border-radius:2.5mm;overflow:hidden}}
.ph img{{width:100%;height:100%;object-fit:cover;display:block}}
.noimg{{height:100%;display:flex;align-items:center;justify-content:center;color:#bbb2a4;font:600 12pt FL,FX,serif}}
.off{{position:absolute;top:2.5mm;left:2.5mm;background:var(--sale);color:#fff;font-weight:600;font-size:8pt;padding:.8mm 2.4mm;border-radius:5mm}}
.tx{{padding:2.6mm .5mm 0}}
.nm{{font-weight:500;font-size:8.6pt;line-height:1.28;height:8.4mm;overflow:hidden}}
.pr{{margin-top:1mm;white-space:nowrap}}
.now{{font-weight:600;font-size:11pt;color:var(--acc)}}
.old{{margin-left:2mm;font-size:8pt;color:#9a9388;text-decoration:line-through}}
.cd{{font-size:7.5pt;color:#9a9388;margin-top:.6mm}}
.back{{page:back;page-break-before:always;height:297mm;background:var(--acc);color:#fff;padding:0 18mm;display:flex;flex-direction:column;justify-content:center}}
.back h2{{font-size:36pt;margin:0 0 6mm;line-height:1.05}}
.back p{{font-size:12pt;color:#d5ebe8;margin:0 0 4mm;max-width:140mm}}
.btn{{align-self:flex-start;display:inline-block;margin-top:8mm;background:#fff;color:var(--acc);font-weight:600;font-size:13pt;padding:4mm 9mm;border-radius:10mm}}
.small{{margin-top:14mm;font-size:8.5pt;color:#a9d0cb}}
</style></head><body>
<div class="cover"><div class="wall">{wall}</div><div class="fade"></div>
<div class="topbar"><p class="brand">HIKWO</p><span class="pill"><i></i>Her gün güncellenir · {date}</span></div>
<div class="ct"><h1>{e(t_main)}<em>{e(t_last)}</em></h1>
<p class="lead">Taş tozu, alçı ve mum dökümü için {len(products)} silikon kalıp. Ürünlere dokunun, sipariş sayfası açılsın.</p></div>
<div class="facts"><div class="f"><b>{len(products)}</b><span>ürün</span></div>
<div class="f hl"><b>%{max_off}</b><span>en yüksek indirim</span></div>
<div class="f"><b>{fmt_tl(cheapest).replace(",00","")}</b><span>başlayan fiyatlar</span></div>
<div class="f"><b>{len(secs)}</b><span>bölüm</span></div></div></div>
<div class="intro"><h2>İçindekiler</h2><p class="sub">Fiyatlar {date} tarihinde hikwo.com'dan alınmıştır; katalog her gün otomatik güncellenir.</p>
{toc}
<div class="how"><div><b>Ürüne dokunun</b><span>Her ürün kartı hikwo.com'daki ürün sayfasına bağlıdır.</span></div>
<div><b>Güncel fiyat</b><span>Katalog her sabah yeniden üretilir; indirimler anında yansır.</span></div>
<div><b>Sipariş</b><span>Siparişlerinizi www.hikwo.com üzerinden verebilirsiniz.</span></div></div>
</div><section class="sec"><header class="sh"><div class="sn">★</div><div><h2>Yeni gelenler</h2><p>Kataloğa en son eklenen kalıplar</p></div></header><div class="grid">{new_cards}</div></section>
{body}
<div class="back"><p class="brand" style="color:#bfe0dc">HIKWO</p><h2>Tüm ürünler ve güncel stoklar hikwo.com'da</h2>
<p>Taş tozu, RTV2 kalıp silikonu, vernik, toz boya ve hazır setlerle üretiminizi tamamlayın.</p>
<a class="btn" href="{SITE}">www.hikwo.com</a>
<p class="small">Bu katalog {date} tarihinde otomatik olarak oluşturulmuştur. Fiyatlar değişebilir; güncel fiyat için ürün sayfasını ziyaret edin.</p></div>
</body></html>'''


def landing(products, now, size_mb):
    e = html.escape
    stamp = now.strftime("%d.%m.%Y %H:%M")
    return f'''<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hikwo {e(TITLE)}</title><style>
body{{margin:0;font:17px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:#1d1b18;color:#f3efe8;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
main{{max-width:520px;text-align:center}}p.b{{letter-spacing:.3em;font-weight:600;color:#c7bfb2;font-size:13px}}
h1{{font:600 clamp(32px,7vw,46px)/1.05 Georgia,serif;margin:8px 0 14px}}
a.btn{{align-self:flex-start;display:inline-block;background:#0e5a57;color:#fff;text-decoration:none;font-weight:600;padding:16px 30px;border-radius:999px;margin:18px 0}}
small{{color:#b6ae9f}}</style></head><body><main><p class="b">HIKWO</p><h1>{e(TITLE)}</h1>
<p>{len(products)} ürün, güncel fiyatlarla. Katalog her gün otomatik yenilenir.</p>
<a class="btn" href="katalog.pdf">PDF kataloğu aç ({size_mb:.1f} MB)</a><br><small>Son güncelleme: {stamp}</small></main></body></html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="test için ürün JSON dosyası (sitenin yerine)")
    a = ap.parse_args()
    now = datetime.now(TR_TZ)
    if a.sample:
        products, total = json.loads(Path(a.sample).read_text()), None
    else:
        products, total = scrape()
    if len(products) < 5:
        raise SystemExit(f"Çok az ürün bulundu ({len(products)}); site yapısı değişmiş olabilir, PDF güncellenmedi.")
    if total and len(products) < total * 0.6:
        print(f"UYARI: sitede {total} ürün görünüyor ama {len(products)} okunabildi", file=sys.stderr)
    OUT.mkdir(exist_ok=True)
    from weasyprint import HTML
    doc = build_html(products, now)
    rendered = HTML(string=doc, base_url=str(ROOT)).render()
    section_pages = {}
    for n, pg in enumerate(rendered.pages, 1):
        for a in pg.anchors:
            section_pages.setdefault(a, n)
    rendered.write_pdf(OUT / "katalog.pdf")
    size = (OUT / "katalog.pdf").stat().st_size / 1e6
    import landing as web
    web.save_images(products, OUT)
    page = web.render(products, group(products), section_pages, now, size, TITLE, SITE, clean_name, code_of)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    (OUT / "urunler.json").write_text(json.dumps(
        [{k: v for k, v in p.items() if k not in ("imgdata", "web")} for p in products], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Tamam: {len(products)} ürün, katalog.pdf {size:.1f} MB")


if __name__ == "__main__":
    main()
