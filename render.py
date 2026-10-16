#!/usr/bin/env python3
"""Genere index.html (fichier unique, autonome) depuis data/items.json."""
import os, json, base64, urllib.request, re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "_site", "index.html")
TZ = ZoneInfo("Europe/Paris")

FONT_CSS = "https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
MONTHS = ["janv.", "fevr.", "mars", "avr.", "mai", "juin", "juil.", "aout", "sept.", "oct.", "nov.", "dec."]
MONTHS = ["janv.", "f\u00e9vr.", "mars", "avr.", "mai", "juin", "juil.", "ao\u00fbt", "sept.", "oct.", "nov.", "d\u00e9c."]


def fetch_fonts():
    """Telecharge les polices et les integre en base64 (page 100% autonome)."""
    try:
        req = urllib.request.Request(FONT_CSS, headers={"User-Agent": UA})
        css = urllib.request.urlopen(req, timeout=25).read().decode("utf-8")
    except Exception as e:
        print("polices: echec CSS ->", e)
        return ""
    blocks = re.findall(r"@font-face\s*\{(.*?)\}", css, re.S)
    out, seen = [], set()
    for b in blocks:
        fam = re.search(r"font-family:\s*'([^']+)'", b)
        wt = re.search(r"font-weight:\s*(\d+)", b)
        st = re.search(r"font-style:\s*(\w+)", b)
        ur = re.search(r"unicode-range:\s*([^;]+)", b)
        src = re.search(r"url\((https://[^)]+\.woff2)\)", b)
        if not (fam and wt and src):
            continue
        rng = (ur.group(1) if ur else "").strip()
        # ne garder que le sous-ensemble latin de base
        if ur and not re.search(r"U\+0000-00FF", rng):
            continue
        if "latin-ext" in b or "cyrillic" in b or "greek" in b or "vietnamese" in b:
            continue
        key = (fam.group(1), wt.group(1), st.group(1) if st else "normal")
        if key in seen:
            continue
        seen.add(key)
        try:
            r2 = urllib.request.Request(src.group(1), headers={"User-Agent": UA})
            blob = urllib.request.urlopen(r2, timeout=25).read()
        except Exception:
            continue
        b64 = base64.b64encode(blob).decode("ascii")
        cstyle = st.group(1) if st else "normal"
        out.append("@font-face{font-family:'%s';font-style:%s;font-weight:%s;font-display:swap;"
                   "src:url(data:font/woff2;base64,%s) format('woff2');}" % (key[0], cstyle, key[1], b64))
    print("polices integrees:", len(out))
    return "\n".join(out)


def rel(dt, now):
    d = now - dt
    s = d.total_seconds()
    if s < 3600:
        m = max(1, int(s // 60))
        return "il y a %d min" % m
    if s < 86400:
        return "il y a %d h" % int(s // 3600)
    if dt.date() == (now - timedelta(days=1)).date():
        return "hier, %02d:%02d" % (dt.hour, dt.minute)
    if d.days < 7:
        return "il y a %d j" % d.days
    return "%d %s" % (dt.day, MONTHS[dt.month - 1])


def band(dt, now):
    if dt >= now - timedelta(hours=12):
        return 0
    if dt.date() == now.date():
        return 1
    if dt.date() == (now - timedelta(days=1)).date():
        return 2
    if (now - dt).days <= 7:
        return 3
    return 4


BANDS = [
    ("Derni\u00e8res 12 heures", "le fil chaud", "band-hot"),
    ("Plus t\u00f4t aujourd'hui", "le reste de la journ\u00e9e", "band-today"),
    ("Hier", "le r\u00e9cap de la veille", "band-yest"),
    ("Cette semaine", "jusqu'\u00e0 7 jours", "band-week"),
    ("Plus ancien", "archive du fil", "band-old"),
]

CHIP_ORDER = ["Phillies Nation", "The Good Phight", "Crossing Broad", "NBC Sports Philadelphia",
              "PhillyVoice", "The Liberty Line", "Phuture Phillies", "Phillies Minor Thoughts",
              "That Balls Outta Here", "MLB Trade Rumors",
              "r/phillies", "Presse"]


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def main():
    with open(os.path.join(DATA, "items.json"), encoding="utf-8") as f:
        d = json.load(f)
    now = datetime.now(TZ)
    fonts = fetch_fonts()

    items = []
    for it in d["items"]:
        dt = datetime.fromisoformat(it["when"]).astimezone(TZ) if it["when"] else now
        items.append({**it, "_dt": dt, "_band": band(dt, now), "_rel": rel(dt, now),
                      "_h": "%02d:%02d" % (dt.hour, dt.minute)})
    items.sort(key=lambda x: x["_dt"], reverse=True)

    counts = {}
    for it in items:
        counts[(it.get("chip") or "?")] = counts.get((it.get("chip") or "?"), 0) + 1
    chips = [c for c in CHIP_ORDER if counts.get(c)] + [c for c in counts if c not in CHIP_ORDER]

    live = [s for s in d["sources"] if s["ok"]]
    dead = [s for s in d["sources"] if not s["ok"]]
    gen = datetime.fromisoformat(d["generated"]).astimezone(TZ)

    cards = []
    for i, it in enumerate(items):
        cards.append(
            '<article class="card" data-source="{src}" data-text="{txt}" data-band="{b}" '
            'data-age="{age:.1f}">'
            '<div class="card-top">'
            '<span class="bug">{pub}</span>'
            '<span class="meta">{h} <i>&middot;</i> {rel}</span>'
            '<a class="orig" href="{url}" target="_blank" rel="noopener">Original&nbsp;<span aria-hidden="true">\u2197</span></a>'
            '</div>'
            '<h3 class="head"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>'
            '{summ}'
            '</article>'.format(
                src=esc((it.get("chip") or "?")), pub=esc(it.get("publisher") or "?"), txt=esc((it["title"] + " " + it["summary"] + " " + it.get("publisher","") + " " + it.get("chip","")).lower()),
                b=it["_band"], age=(now - it["_dt"]).total_seconds() / 3600,
                h=it["_h"], rel=esc(it["_rel"]), url=esc(it["url"]), title=esc(it["title"]),
                summ=('<p class="sum">%s</p>' % esc(it["summary"])) if it["summary"] else ""))
    body = []
    for bi, (title, sub, cls) in enumerate(BANDS):
        group = [c for c, it in zip(cards, items) if it["_band"] == bi]
        if not group:
            continue
        body.append(
            '<section class="band %s" data-band="%d">'
            '<header class="band-head"><h2>%s</h2><span class="band-sub">%s</span>'
            '<span class="band-n">%d</span></header><div class="feed">%s</div></section>'
            % (cls, bi, title, sub, len(group), "".join(group)))

    tick_items = "".join(
        '<span class="tick"><b>%s</b> %s</span>' % (esc((it.get("chip") or "?").upper()), esc(it["title"]))
        for it in items[:6])
    src_rows = "".join(
        '<li class="%s"><span class="dot"></span><span class="sname">%s</span>'
        '<span class="scount">%d</span><a class="slink" href="%s" target="_blank" rel="noopener">\u2197</a></li>'
        % ("on" if s["ok"] else "off", esc(s["source"]), s["n"], esc(s["site"]))
        for s in sorted(d["sources"], key=lambda x: -x["n"]))

    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fil Phillies \u2014 agr\u00e9gateur de presse</title>
<meta name="description" content="Toutes les news des Phillies de Philadelphie, agr\u00e9g\u00e9es depuis les meilleurs flux, avec le lien vers chaque article original.">
<style>
__FONTS__
:root{
  --ink:#0C1016; --panel:#141A22; --panel2:#1B232D; --rule:#29323D;
  --chalk:#EEF1F4; --dim:#A9B3C1; --red:#E81828; --reddim:#A8101D;
  --disp:'Archivo Narrow','Arial Narrow',system-ui,sans-serif;
  --body:'IBM Plex Sans',system-ui,-apple-system,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,'SFMono-Regular',monospace;
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:var(--ink); color:var(--chalk); font-family:var(--body);
  font-size:15px; line-height:1.6; -webkit-font-smoothing:antialiased;
  background-image:radial-gradient(120% 60% at 50% -10%,rgba(232,24,40,.13),transparent 60%);
  background-repeat:no-repeat;
}
a{color:inherit}
.wrap{max-width:1140px;margin:0 auto;padding:0 22px}

/* ---------- masthead ---------- */
.topbar{border-bottom:1px solid var(--rule);background:linear-gradient(180deg,#10161E,#0C1016)}
.mast{display:flex;align-items:flex-end;gap:22px;flex-wrap:wrap;padding:26px 0 18px}
.wordmark{font-family:var(--disp);font-weight:700;font-size:clamp(42px,10vw,86px);line-height:.82;
  letter-spacing:-.015em;text-transform:uppercase;margin:0}
.wordmark em{font-style:normal;color:var(--red)}
.mast-side{padding-bottom:6px;min-width:210px}
.eyebrow{font-family:var(--disp);font-weight:600;font-size:12px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim);margin:0 0 6px}
.stamp{font-family:var(--mono);font-size:11.5px;color:var(--chalk);opacity:.85}
.stamp b{color:var(--red);font-weight:500}
.counts{display:flex;gap:26px;margin-top:12px;padding-bottom:16px;border-bottom:1px solid var(--rule)}
.stat{display:flex;flex-direction:column}
.stat b{font-family:var(--disp);font-weight:700;font-size:26px;line-height:1}
.stat span{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-top:4px}

/* ---------- ticker ---------- */
.ticker{display:flex;align-items:center;gap:0;border-bottom:1px solid var(--rule);background:#0A0E13;overflow:hidden}
.ticker-label{flex:0 0 auto;background:var(--red);color:#fff;font-family:var(--disp);font-weight:700;
  font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;padding:9px 14px;display:flex;align-items:center;gap:7px}
.pulse{width:6px;height:6px;border-radius:50%;background:#fff;animation:pulse 1.8s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.ticker-window{flex:1;min-width:0;overflow:hidden;margin-left:16px;mask-image:linear-gradient(90deg,transparent 0,#000 30px,#000 calc(100% - 46px),transparent 100%);-webkit-mask-image:linear-gradient(90deg,transparent 0,#000 30px,#000 calc(100% - 46px),transparent 100%)}
.ticker-track{display:flex;width:max-content;gap:44px;padding:0 18px;white-space:nowrap;animation:slide 46s linear infinite}
.tick{font-family:var(--mono);font-size:11.5px;color:var(--dim)}
.tick b{color:var(--chalk);font-weight:500;margin-right:8px;font-family:var(--disp);letter-spacing:.1em;font-size:11px}
@keyframes slide{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@media (prefers-reduced-motion:reduce){.ticker-track{animation:none}.pulse{animation:none}}

/* ---------- controls ---------- */
.controls{position:sticky;top:0;z-index:20;background:rgba(12,16,22,.94);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--rule);padding:12px 0}
.ctrl-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.search{flex:1 1 230px;display:flex;align-items:center;gap:9px;background:var(--panel);
  border:1px solid var(--rule);border-radius:2px;padding:9px 12px}
.search:focus-within{border-color:var(--reddim)}
.search svg{flex:0 0 auto;opacity:.5}
.search input{flex:1;background:none;border:0;outline:0;color:var(--chalk);font-family:var(--mono);font-size:12.5px}
.search input::placeholder{color:var(--dim)}
.kbd{font-family:var(--mono);font-size:10px;color:var(--dim);border:1px solid var(--rule);border-radius:2px;padding:1px 5px}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px;
  scrollbar-width:none;-ms-overflow-style:none}
.chips::-webkit-scrollbar{display:none}
.chip{font-family:var(--disp);font-weight:600;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
  background:transparent;color:var(--dim);border:1px solid var(--rule);border-radius:2px;
  min-height:44px;padding:0 13px;cursor:pointer;display:flex;gap:6px;align-items:center;transition:.14s}
.chip:hover{color:var(--chalk);border-color:var(--dim)}
.chip[aria-pressed="true"]{background:var(--red);border-color:var(--red);color:#fff}
.chip i{font-style:normal;font-family:var(--mono);font-size:10.5px;opacity:.7}
.reset{font-family:var(--mono);font-size:11px;background:none;border:0;color:var(--dim);
  text-decoration:underline;cursor:pointer;padding:6px 2px}
.reset:hover{color:var(--chalk)}

/* ---------- layout ---------- */
.layout{display:grid;grid-template-columns:1fr;gap:38px;padding:34px 0 10px}
@media (min-width:1040px){.layout{grid-template-columns:minmax(0,1fr) 268px}}
.lead{border-left:3px solid var(--red);padding:2px 0 2px 16px;margin-bottom:34px}
.lead p{margin:0;color:var(--dim);max-width:64ch;font-size:14px}
.lead strong{color:var(--chalk);font-weight:600}

.band{margin-bottom:38px}
.band-head{display:flex;align-items:baseline;gap:12px;border-bottom:2px solid var(--rule);padding-bottom:8px;margin-bottom:0}
.band-head h2{font-family:var(--disp);font-weight:700;font-size:19px;letter-spacing:.04em;
  text-transform:uppercase;margin:0}
.band-hot .band-head{border-bottom-color:var(--red)}
.band-hot .band-head h2{color:var(--red)}
.band-sub{font-family:var(--mono);font-size:10.5px;color:var(--dim);letter-spacing:.04em}
.band-n{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--dim)}
.band-n:after{content:" art."}

.card{border-bottom:1px solid var(--rule);padding:20px 14px 20px 15px;position:relative;
  border-left:3px solid transparent;transition:background .15s,border-color .15s}
.card:hover{background:var(--panel);border-left-color:var(--red)}
.card-top{display:flex;align-items:center;gap:12px;margin-bottom:9px;flex-wrap:wrap}
.bug{font-family:var(--disp);font-weight:700;font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;
  background:var(--red);color:#fff;padding:3px 8px 2px;border-radius:1px;white-space:nowrap}
.meta{font-family:var(--mono);font-size:11px;color:var(--dim)}
.meta i{font-style:normal;opacity:.5}
.orig{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--dim);text-decoration:none;
  border-bottom:1px solid transparent;white-space:nowrap}
.orig:hover{color:var(--red);border-bottom-color:var(--red)}
.head{font-family:var(--disp);font-weight:600;font-size:clamp(18px,2.3vw,23px);line-height:1.16;
  letter-spacing:.002em;margin:0 0 8px}
.head a{text-decoration:none}
.head a:hover{color:#fff;text-decoration:underline;text-decoration-color:var(--red);text-underline-offset:4px}
.sum{margin:0;color:var(--dim);font-size:14px;max-width:74ch}

/* ---------- aside ---------- */
aside{display:flex;flex-direction:column;gap:22px}
@media (min-width:1040px){aside{position:sticky;top:132px;align-self:start;max-height:calc(100vh - 160px);overflow:auto}}
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:2px;padding:16px}
.panel h3{font-family:var(--disp);font-weight:700;font-size:13px;letter-spacing:.16em;
  text-transform:uppercase;margin:0 0 12px;color:var(--chalk)}
.panel p{margin:0;font-size:13px;color:var(--dim)}
.srclist{list-style:none;margin:0;padding:0}
.srclist li{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px dotted var(--rule);font-size:13px}
.srclist li:last-child{border-bottom:0}
.dot{width:6px;height:6px;border-radius:50%;flex:0 0 auto;background:var(--red)}
.srclist li.off .dot{background:#4A5461}
.srclist li.off .sname{color:var(--dim);text-decoration:line-through;text-decoration-color:#4A5461}
.sname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.scount{font-family:var(--mono);font-size:11px;color:var(--dim)}
.slink{font-family:var(--mono);font-size:11px;color:var(--dim);text-decoration:none}
.slink:hover{color:var(--red)}
.free li{padding:5px 0}
.free{list-style:none;margin:0;padding:0;font-size:13px;color:var(--dim)}
.free b{color:var(--chalk);font-weight:600}

.empty{display:none;padding:56px 20px;text-align:center;border:1px dashed var(--rule);border-radius:2px}
.empty.on{display:block}
.empty h3{font-family:var(--disp);font-size:20px;text-transform:uppercase;letter-spacing:.05em;margin:0 0 8px}
.empty p{color:var(--dim);margin:0 auto;max-width:44ch;font-size:14px}

footer{border-top:1px solid var(--rule);margin-top:26px;padding:26px 0 54px;color:var(--dim);font-size:12.5px}
footer .note{max-width:78ch}
footer .note b{color:var(--chalk)}
@media (max-width:600px){
  .wrap{padding:0 15px}
  .mast{padding:20px 0 14px;gap:14px}
  .mast-side{min-width:0}
  .counts{gap:14px 20px;flex-wrap:wrap}
  .stat b{font-size:21px}
  .ticker-label{padding:8px 10px;font-size:10px;letter-spacing:.12em}
  .tick{font-size:10.5px}
  .controls{padding:10px 0}
  .search{flex:1 1 100%}
  .kbd{display:none}
  .reset{margin-left:auto}
  .lead{padding-left:12px;margin-bottom:26px}
  .card{padding:17px 10px 17px 12px}
  .chips{flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;
    -webkit-overflow-scrolling:touch;padding-bottom:2px}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:0 0 auto;padding:0 12px}
  .card-top{gap:9px}
  .orig{margin-left:auto}
  .band-head h2{font-size:16px}
  .band-sub{display:none}
  .layout{gap:28px;padding-top:26px}
}
:focus-visible{outline:2px solid var(--red);outline-offset:2px}
</style>
</head>
<body>
<header class="topbar">
  <div class="wrap">
    <div class="mast">
      <h1 class="wordmark">Phil<em>lies</em><br>Fil de presse</h1>
      <div class="mast-side">
        <p class="eyebrow">Agr\u00e9gateur \u00b7 MLB \u00b7 Philadelphia</p>
        <p class="stamp"><b>MAJ</b> __STAMP__ \u00b7 heure de Paris</p>
      </div>
    </div>
    <div class="counts">
      <div class="stat"><b>__N__</b><span>articles suivis</span></div>
      <div class="stat"><b>__NLIVE__</b><span>sources actives</span></div>
      <div class="stat"><b>__NDEAD__</b><span>flux en panne</span></div>
      <div class="stat"><b>__FRESH__</b><span>il y a moins de 12 h</span></div>
    </div>
  </div>
  <div class="ticker">
    <div class="ticker-label"><span class="pulse"></span>\u00c0 la une</div>
    <div class="ticker-window"><div class="ticker-track">__TICKS____TICKS__</div></div>
  </div>
</header>

<div class="controls">
  <div class="wrap">
    <div class="ctrl-row">
      <label class="search">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>
        <input id="q" type="search" placeholder="Chercher dans les titres et extraits (en anglais)" aria-label="Rechercher">
        <span class="kbd">/</span>
      </label>
      <button class="reset" id="reset" type="button">R\u00e9initialiser</button>
    </div>
    <div class="chips" id="chips">
      <button class="chip" data-src="*" aria-pressed="true">Tout <i>__N__</i></button>
      __CHIPS__
    </div>
  </div>
</div>

<div class="wrap">
  <div class="layout">
    <main>
      <div class="lead">
        <p><strong>Z\u00e9ro traduction, z\u00e9ro abonnement.</strong> Les titres et extraits sont affich\u00e9s dans leur
        langue d'origine, tels que publi\u00e9s par chaque r\u00e9daction. Chaque carte renvoie \u00e0 l'article complet
        chez la source, qui seule per\u00e7oit son audience.</p>
      </div>
      __BODY__
      <div class="empty" id="empty">
        <h3>Aucun article</h3>
        <p>Rien ne correspond \u00e0 cette recherche dans les flux actuels. Essayez un autre mot, ou r\u00e9initialisez les filtres.</p>
      </div>
    </main>
    <aside>
      <div class="panel">
        <h3>Sources surveill\u00e9es</h3>
        <ul class="srclist">__SRCROWS__</ul>
      </div>
      <div class="panel">
        <h3>Pourquoi c'est gratuit</h3>
        <ul class="free">
          <li><b>Collecte</b> \u2014 flux RSS, Reddit et Bing News, aucune API payante</li>
          <li><b>Ex\u00e9cution</b> \u2014 cron GitHub Actions, palier gratuit</li>
          <li><b>H\u00e9bergement</b> \u2014 page statique, h\u00e9bergement gratuit</li>
          <li><b>Stockage</b> \u2014 un fichier JSON, pas de base de donn\u00e9es</li>
          <li><b>Traduction</b> \u2014 supprim\u00e9e du p\u00e9rim\u00e8tre</li>
        </ul>
      </div>
    </aside>
  </div>
  <footer>
    <p class="note"><b>Prototype.</b> Donn\u00e9es collect\u00e9es \u00e0 __STAMP__ depuis les flux RSS publics list\u00e9s ci-dessus.
    Titres, extraits et marques appartiennent \u00e0 leurs auteurs respectifs ; cette page n'en affiche que des
    amorces et renvoie syst\u00e9matiquement \u00e0 l'article original.</p>
  </footer>
</div>

<script>
(function(){
  var cards=[].slice.call(document.querySelectorAll('.card')),
      bands=[].slice.call(document.querySelectorAll('.band')),
      chips=[].slice.call(document.querySelectorAll('.chip')),
      q=document.getElementById('q'), empty=document.getElementById('empty'),
      active='*';
  if(window.innerWidth<600){q.placeholder='Chercher\u2026';}
  function apply(){
    var t=(q.value||'').trim().toLowerCase(), shown=0;
    cards.forEach(function(c){
      var okS=(active==='*'||c.dataset.source===active),
          okT=(!t||c.dataset.text.indexOf(t)>-1);
      var ok=okS&&okT;
      c.hidden=!ok; if(ok) shown++;
    });
    bands.forEach(function(b){
      var any=[].slice.call(b.querySelectorAll('.card')).some(function(c){return !c.hidden;});
      b.hidden=!any;
    });
    empty.classList.toggle('on',shown===0);
  }
  chips.forEach(function(ch){
    ch.addEventListener('click',function(){
      active=ch.dataset.src;
      chips.forEach(function(o){o.setAttribute('aria-pressed',String(o===ch));});
      apply();
    });
  });
  q.addEventListener('input',apply);
  document.getElementById('reset').addEventListener('click',function(){
    q.value='';active='*';
    chips.forEach(function(o){o.setAttribute('aria-pressed',String(o.dataset.src==='*'));});
    apply();
  });
  /* Fondu du bord de la rangee de puces, pilote par la position de defilement :
     present tant qu'il reste du contenu de ce cote, retire en debut/fin de liste. */
  var chipsRow=document.getElementById('chips');
  function chipsFade(){
    if(!chipsRow) return;
    function clear(){chipsRow.style.maskImage='';chipsRow.style.webkitMaskImage='';}
    if(window.innerWidth>=600){clear();return;}
    var max=chipsRow.scrollWidth-chipsRow.clientWidth;
    if(max<=1){clear();return;}
    var left=(chipsRow.scrollLeft<=3)?0:22,
        right=(chipsRow.scrollLeft>=max-3)?0:30, g;
    if(!left&&!right){clear();return;}
    g='linear-gradient(90deg,transparent 0,#000 '+left+'px,#000 calc(100% - '+right+'px),transparent 100%)';
    chipsRow.style.maskImage=g; chipsRow.style.webkitMaskImage=g;
  }
  if(chipsRow){
    chipsRow.addEventListener('scroll',chipsFade,{passive:true});
    window.addEventListener('resize',chipsFade);
    window.addEventListener('orientationchange',chipsFade);
    if(document.fonts&&document.fonts.ready){document.fonts.ready.then(chipsFade);}
    chipsFade();
  }
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus();}
    if(e.key==='Escape'&&document.activeElement===q){q.value='';apply();q.blur();}
  });
})();
</script>
</body>
</html>"""

    fresh = len([i for i in items if i["_band"] == 0])
    html = (html.replace("__FONTS__", fonts)
                .replace("__STAMP__", now.strftime("%d/%m/%Y \u00e0 %H:%M"))
                .replace("__TICKS__", tick_items)
                .replace("__SRCROWS__", src_rows)
                .replace("__CHIPS__", "".join(
                    '<button class="chip" data-src="%s" aria-pressed="false">%s <i>%d</i></button>'
                    % (esc(c), esc(c), counts[c]) for c in chips))
                .replace("__BODY__", "".join(body))
                .replace("__FRESH__", str(fresh))
                .replace("__NLIVE__", str(len(live)))
                .replace("__NDEAD__", str(len(dead)))
                .replace("__N__", str(len(items))))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("ecrit:", OUT, os.path.getsize(OUT) // 1024, "Ko |", len(items), "cartes")


if __name__ == "__main__":
    main()
