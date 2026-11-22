"""Kataloğun web giriş sayfası (site/index.html)."""
import base64, html
from pathlib import Path

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
e = html.escape


def _tl(n):
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.replace(",00", "") + " TL"


def save_images(products, out: Path):
    """Kullanılacak ürün görsellerini site/img/ altına yazar, p['web'] yolunu ekler."""
    d = out / "img"
    d.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(products):
        data = p.get("imgdata", "")
        if not data.startswith("data:image"):
            continue
        name = f"{p.get('pid') or i}.jpg"
        (d / name).write_bytes(base64.b64decode(data.split(",", 1)[1]))
        p["web"] = "img/" + name


def render(products, sections, section_pages, now, size_mb, title, site, clean_name, code_of):
    size_txt = f"{size_mb:.0f} MB" if size_mb >= 1 else f"{size_mb*1000:.0f} KB"
    date = f"{now.day} {MONTHS[now.month - 1]} {now.year}"
    stamp = f"{date}, {now:%H:%M}"
    withimg = [p for p in products if p.get("web")]
    newest = sorted(withimg, key=lambda p: -p["pid"])
    deals = sorted([p for p in withimg if p.get("old")], key=lambda p: p["price"] / p["old"])[:8]
    max_off = round((1 - deals[0]["price"] / deals[0]["old"]) * 100) if deals else 0
    cheapest = min(p["price"] for p in products)

    # Kayan fotoğraf sütunları (4 sütun, her biri 2 kez tekrar ederek sonsuz döngü)
    pool = newest[:32] or withimg
    cols = ""
    for c in range(4):
        imgs = pool[c::4] or pool
        strip = "".join(f'<img src="{e(p["web"])}" alt="" loading="lazy">' for p in imgs)
        cols += f'<div class="col c{c}"><div class="track">{strip}{strip}</div></div>'

    def card(p, badge=True):
        off = round((1 - p["price"] / p["old"]) * 100) if p.get("old") else 0
        return f'''<a class="card" href="{e(p["url"])}" target="_blank" rel="noopener">
<div class="ph"><img src="{e(p["web"])}" alt="{e(clean_name(p["name"]))}" loading="lazy">{f'<span class="off">-%{off}</span>' if badge and off >= 5 else ''}</div>
<p class="nm">{e(clean_name(p["name"]))}</p>
<p class="pr"><b>{_tl(p["price"])}</b>{f'<s>{_tl(p["old"])}</s>' if p.get("old") else ''}</p></a>'''

    cats = ""
    for i, (t, d, lst) in enumerate(sections):
        rep = next((p for p in sorted(lst, key=lambda p: -p["pid"]) if p.get("web")), None)
        pg = section_pages.get(f"s{i}")
        href = f"katalog.pdf#page={pg}" if pg else "katalog.pdf"
        cats += f'''<a class="cat" href="{href}">{f'<img src="{e(rep["web"])}" alt="" loading="lazy">' if rep else ''}
<span class="shade"></span><span class="ct"><b>{e(t)}</b><small>{len(lst)} ürün{f" · sayfa {pg}" if pg else ""}</small></span></a>'''

    return f'''<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hikwo · {e(title)}</title>
<meta name="description" content="{len(products)} silikon kalıp, güncel fiyatlarla. Her gün otomatik güncellenen PDF katalog.">
<meta property="og:title" content="Hikwo · {e(title)}">
<meta property="og:description" content="{len(products)} ürün · %{max_off}'e varan indirim · {date} itibarıyla güncel">
{f'<meta property="og:image" content="{e(newest[0]["web"])}">' if newest else ''}
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--ink:#141210;--ink2:#1f1c18;--stone:#f3efe8;--sand:#e6dfd3;--mute:#a59d90;--acc:#13706b;--acc2:#5fd0c4;--sale:#d2553a}}
*{{box-sizing:border-box;min-width:0}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--stone);color:var(--ink);font:16px/1.55 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;overflow-x:clip}}
a{{color:inherit;text-decoration:none}}
img{{display:block}}
.serif{{font-family:Fraunces,Georgia,serif}}

/* HERO */
.hero{{position:relative;min-height:100svh;background:var(--ink);color:#fff;display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);overflow:hidden}}
.copy{{position:relative;z-index:2;padding:clamp(28px,5vw,72px) max(5vw,20px);display:flex;flex-direction:column;justify-content:center;gap:26px}}
.top{{position:absolute;top:clamp(20px,3vw,36px);left:max(5vw,20px);right:max(5vw,20px);display:flex;justify-content:space-between;align-items:center;z-index:3}}
.logo{{font-weight:600;letter-spacing:.34em;font-size:14px}}
.live{{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:#d9d2c6;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);padding:7px 14px;border-radius:999px;backdrop-filter:blur(8px)}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--acc2);box-shadow:0 0 0 0 rgba(95,208,196,.6);animation:pulse 2s infinite}}
@keyframes pulse{{70%{{box-shadow:0 0 0 10px rgba(95,208,196,0)}}100%{{box-shadow:0 0 0 0 rgba(95,208,196,0)}}}}
h1{{font:700 clamp(44px,7.2vw,96px)/.98 Fraunces,Georgia,serif;margin:0;letter-spacing:-.02em;text-wrap:balance}}
h1 em{{font-style:italic;font-weight:500;color:var(--acc2)}}
.lead{{font-size:clamp(16px,1.6vw,19px);color:#cfc7ba;max-width:34ch;margin:0}}
.ctas{{display:flex;flex-wrap:wrap;gap:12px}}
.btn{{display:inline-flex;align-items:center;gap:12px;min-height:56px;padding:0 28px;border-radius:999px;font-weight:600;font-size:17px;transition:transform .2s,box-shadow .2s,background .2s}}
.btn.pri{{background:var(--acc2);color:var(--ink)}}
.btn.pri:hover{{transform:translateY(-2px);box-shadow:0 14px 34px rgba(95,208,196,.35)}}
.btn.sec{{border:1px solid rgba(255,255,255,.25);color:#fff}}
.btn.sec:hover{{background:rgba(255,255,255,.08)}}
.btn svg{{width:20px;height:20px}}
.btn small{{font-weight:500;opacity:.7;font-size:14px}}
.stats{{display:flex;gap:clamp(18px,3vw,44px);flex-wrap:wrap;border-top:1px solid rgba(255,255,255,.12);padding-top:22px;margin-top:6px}}
.stat b{{display:block;font:700 clamp(26px,3vw,38px)/1 Fraunces,Georgia,serif;color:#fff}}
.stat span{{font-size:13px;color:var(--mute)}}
.wall{{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:0 12px;transform:rotate(-6deg) scale(1.18);transform-origin:center}}
.wall::before,.wall::after{{content:"";position:absolute;left:-20%;right:-20%;height:22%;z-index:2;pointer-events:none}}
.wall::before{{top:-2%;background:linear-gradient(var(--ink),transparent)}}
.wall::after{{bottom:-2%;background:linear-gradient(transparent,var(--ink))}}
.col{{overflow:hidden;height:130svh;margin-top:-15svh}}
.track{{display:flex;flex-direction:column;gap:12px;animation:up 60s linear infinite}}
.c1 .track,.c3 .track{{animation-name:down;animation-duration:72s}}
.c2 .track{{animation-duration:54s}}
.track img{{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:16px;background:#2a2621}}
@keyframes up{{to{{transform:translateY(-50%)}}}}
@keyframes down{{from{{transform:translateY(-50%)}}to{{transform:translateY(0)}}}}
.hero::after{{content:"";position:absolute;inset:0 auto 0 0;width:58%;background:linear-gradient(90deg,var(--ink) 55%,transparent);z-index:1;pointer-events:none}}

/* SECTIONS */
.band{{padding:clamp(48px,7vw,104px) max(5vw,20px)}}
.wrap{{max-width:1240px;margin:0 auto}}
.head{{display:flex;justify-content:space-between;align-items:end;gap:20px;flex-wrap:wrap;margin-bottom:28px}}
h2{{font:700 clamp(30px,4vw,48px)/1.05 Fraunces,Georgia,serif;margin:0;letter-spacing:-.01em}}
.head p{{margin:6px 0 0;color:#6e685f}}
.more{{font-weight:600;color:var(--acc);white-space:nowrap}}
.cats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}
.cat{{position:relative;aspect-ratio:4/5;border-radius:20px;overflow:hidden;background:var(--ink2);color:#fff}}
.cat:first-child{{grid-column:span 2;grid-row:span 2;aspect-ratio:auto}}
.cat img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transition:transform .6s}}
.cat:hover img{{transform:scale(1.06)}}
.shade{{position:absolute;inset:0;background:linear-gradient(180deg,transparent 45%,rgba(14,12,10,.82))}}
.ct{{position:absolute;left:18px;right:18px;bottom:16px}}
.ct b{{display:block;font:700 clamp(19px,2vw,26px)/1.1 Fraunces,Georgia,serif}}
.cat:first-child .ct b{{font-size:clamp(26px,3.4vw,42px)}}
.ct small{{font-size:13px;color:#e4ddd1}}
.rail{{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(220px,1fr);gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:10px;scrollbar-width:thin}}
.card{{scroll-snap-align:start;display:flex;flex-direction:column}}
.ph{{position:relative;aspect-ratio:1;border-radius:18px;overflow:hidden;background:#fff}}
.ph img{{width:100%;height:100%;object-fit:cover;transition:transform .5s}}
.card:hover .ph img{{transform:scale(1.05)}}
.off{{position:absolute;top:12px;left:12px;background:var(--sale);color:#fff;font-weight:600;font-size:13px;padding:4px 10px;border-radius:999px}}
.nm{{margin:12px 2px 4px;font-weight:500;font-size:15px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.pr{{margin:0 2px;white-space:nowrap}}.pr b{{color:var(--acc);font-size:17px}}.pr s{{color:#9a9388;font-size:14px;margin-left:8px}}
.dark{{background:var(--ink);color:#fff}}.dark .head p{{color:var(--mute)}}.dark .ph{{background:#2a2621}}.dark .pr b{{color:var(--acc2)}}.dark .more{{color:var(--acc2)}}
.final{{text-align:center;background:var(--acc);color:#fff}}
.final h2{{max-width:16ch;margin:0 auto 14px}}
.final p{{color:#cdeae6;margin:0 auto 28px;max-width:46ch}}
.final .btn.pri{{background:#fff;color:var(--acc)}}
footer{{padding:28px max(5vw,20px);color:#8a8379;font-size:14px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;background:var(--ink)}}
:focus-visible{{outline:3px solid var(--acc2);outline-offset:3px}}

@media(max-width:900px){{
  .hero{{grid-template-columns:1fr;min-height:auto}}
  .hero::after{{display:none}}
  .copy{{padding-top:96px;padding-bottom:36px}}
  .wall{{order:-1;height:340px;overflow:hidden;transform:rotate(-6deg) scale(1.25);margin-top:40px}}
  .col{{height:520px;margin-top:-90px}}
  .cats{{grid-template-columns:repeat(2,minmax(0,1fr))}}
  .cat:first-child{{grid-row:auto;aspect-ratio:16/10}}
}}
@media(max-width:520px){{.btn{{width:100%;justify-content:center}}.rail{{grid-auto-columns:72%}}}}
@media(prefers-reduced-motion:reduce){{.track,.dot{{animation:none}}html{{scroll-behavior:auto}}}}
</style></head>
<body>
<section class="hero">
  <div class="top"><span class="logo">HIKWO</span><span class="live"><span class="dot"></span>Bugün güncellendi · {e(date)}</span></div>
  <div class="copy">
    <h1>Silikon Kalıp <em>Kataloğu</em></h1>
    <p class="lead">Taş tozu, alçı ve mum dökümü için {len(products)} kalıp. Fiyatlar her sabah siteden otomatik yenilenir.</p>
    <div class="ctas">
      <a class="btn pri" href="katalog.pdf"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12m0 0l-5-5m5 5l5-5M4 21h16"/></svg>PDF Kataloğu Aç <small>{size_txt}</small></a>
      <a class="btn sec" href="{e(site)}" target="_blank" rel="noopener">hikwo.com'a git</a>
    </div>
    <div class="stats">
      <div class="stat"><b>{len(products)}</b><span>ürün</span></div>
      <div class="stat"><b>%{max_off}</b><span>en yüksek indirim</span></div>
      <div class="stat"><b>{_tl(cheapest)}</b><span>başlayan fiyatlar</span></div>
      <div class="stat"><b>{len(sections)}</b><span>bölüm</span></div>
    </div>
  </div>
  <div class="wall" aria-hidden="true">{cols}</div>
</section>

<section class="band"><div class="wrap">
  <div class="head"><div><h2>Bölümler</h2><p>Bir bölüme dokunun, PDF'te o sayfadan açılsın.</p></div><a class="more" href="katalog.pdf">Tüm katalog →</a></div>
  <div class="cats">{cats}</div>
</div></section>

<section class="band dark"><div class="wrap">
  <div class="head"><div><h2>Yeni gelenler</h2><p>Kataloğa en son eklenen kalıplar</p></div><a class="more" href="{e(site)}" target="_blank" rel="noopener">Sitede gör →</a></div>
  <div class="rail">{"".join(card(p) for p in newest[:10])}</div>
</div></section>

<section class="band"><div class="wrap">
  <div class="head"><div><h2>En büyük indirimler</h2><p>Bugünün en avantajlı fiyatları</p></div></div>
  <div class="rail">{"".join(card(p) for p in deals)}</div>
</div></section>

<section class="band final"><div class="wrap">
  <h2>Tüm koleksiyon tek dosyada</h2>
  <p>{len(products)} ürün, fotoğraflar ve güncel fiyatlarla. Ürüne dokunduğunuzda sipariş sayfası açılır.</p>
  <a class="btn pri" href="katalog.pdf">PDF Kataloğu Aç <small>{size_txt}</small></a>
</div></section>
<footer><span>© Hikwo · hikwo.com</span><span>Son güncelleme: {e(stamp)}</span></footer>
</body></html>'''
