#!/usr/bin/env python3
"""Collecte les sources Phillies -> data/items.json.

Sources : flux RSS des redactions, r/phillies (Reddit), Google News.
Aucune API payante, aucune cle, aucun compte.

Fetch HTTP direct avec User-Agent navigateur : indispensable, plusieurs de ces
sites renvoient 403 ou du HTML aux User-Agents de robots (constate sur Reddit
et Phillies Nation).
"""
import os, re, json, html as ht, time, urllib.request, urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
RAW = os.path.join(DATA, "raw")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# --- redactions suivies : (nom, url du flux, site, mode) ---
RSS_FEEDS = [
    ("Phillies Nation", "https://philliesnation.com/feed/",
     "https://philliesnation.com/", "team"),
    ("The Good Phight", "https://www.thegoodphight.com/rss/index.xml",
     "https://www.thegoodphight.com/", "team"),
    ("Crossing Broad", "https://www.crossingbroad.com/feed/",
     "https://www.crossingbroad.com/", "team"),
    ("NBC Sports Philadelphia", "https://www.nbcsportsphiladelphia.com/feed/",
     "https://www.nbcsportsphiladelphia.com/", "team"),
    ("PhillyVoice", "https://www.phillyvoice.com/feed/tag/phillies/",
     "https://www.phillyvoice.com/tags/phillies/", "team"),
    ("The Liberty Line", "https://thelibertyline.com/category/phillies/feed/",
     "https://thelibertyline.com/category/phillies/", "team"),
    ("Phuture Phillies", "https://phuturephillies.com/feed/",
     "https://phuturephillies.com/", "prospects"),
    ("Phillies Minor Thoughts", "https://philliesminorthoughts.com/feed",
     "https://philliesminorthoughts.com/", "prospects"),
    ("That Balls Outta Here", "https://thatballsouttahere.com/feed",
     "https://thatballsouttahere.com/", "team"),
    ("MLB Trade Rumors", "https://www.mlbtraderumors.com/feed",
     "https://www.mlbtraderumors.com/", "filter"),
]

REDDIT_NAME = "r/phillies"
REDDIT_URL = "https://www.reddit.com/r/phillies/.rss?limit=25"
REDDIT_SITE = "https://www.reddit.com/r/phillies/"

NEWS_CHIP = "Presse"
NEWS_SITE = "https://www.bing.com/news"
NEWS_URL = "https://www.bing.com/news/search?q=%s&format=RSS&count=60"
NEWS_QUERIES = [("Presse \u2014 Phillies", "Philadelphia Phillies"),
                ("Presse \u2014 mercato", "Phillies MLB trade signing"),
                ("Presse \u2014 effectif", "Phillies roster injury")]

# plafonds : aucune source ne doit ecraser le fil
CAPS = {"fil": 14, "reddit": 12, "gnews": 30}
TOTAL_CAP = 88
DAYS = 10
JACCARD = 0.55          # seuil de fusion des quasi-doublons de titres
KEYWORDS = ("phillies", "philadelphia", "citizens bank park", "phanatic")
JUNK_PUBLISHERS = ("auction", "savant", "ticket")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
STOP = set("the a an and or of to in for on with at by from is are was were be been will "
           "would can could has have had its his her their this that these those as not "
           "but who what when why how new say says said".split())


# ---------------------------------------------------------------- utilitaires
def fetch(url, timeout=25, tries=3):
    """GET avec UA navigateur + retries.

    Certains serveurs coupent la connexion au premier essai (observé sur
    Phillies Nation) : on retente avec un court backoff.
    """
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": ("application/rss+xml, application/atom+xml, "
                           "application/xml, text/xml, */*"),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Referer": url,
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def local(t):
    return t.split("}")[-1]


def kids(el, name):
    return [c for c in el if local(c.tag) == name]


def text_of(el, *names):
    for n in names:
        for c in kids(el, n):
            if c.text and c.text.strip():
                return c.text.strip()
    return ""


def link_of(el):
    for c in kids(el, "link"):
        rel = (c.get("rel") or "alternate").lower()
        href = c.get("href")
        if href and rel == "alternate":
            return href.strip()
        if c.text and c.text.strip().startswith("http"):
            return c.text.strip()
    for c in kids(el, "guid"):
        if c.text and c.text.strip().startswith("http"):
            return c.text.strip()
    return ""


def clean(s):
    if not s:
        return ""
    return WS_RE.sub(" ", ht.unescape(TAG_RE.sub(" ", s))).strip()


def clip(s, n=230):
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 100 else cut).rstrip(" ,;:.") + "\u2026"


def tokens(t):
    return {w for w in re.findall(r"[a-z0-9']+", (t or "").lower())
            if len(w) > 2 and w not in STOP}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parse_when(raw):
    if not raw:
        return None
    try:
        w = parsedate_to_datetime(raw)
    except Exception:
        try:
            w = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return w.replace(tzinfo=timezone.utc) if w.tzinfo is None else w


def parse_xml(path):
    """Retourne (items, erreur). Gere RSS 2.0 et Atom."""
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        return [], "parse: %s" % e
    tag = local(root.tag)
    if tag == "rss":
        ch = kids(root, "channel")
        nodes = kids(ch[0], "item") if ch else []
    elif tag == "feed":
        nodes = kids(root, "entry")
    elif tag == "RDF":
        nodes = kids(root, "item")
    else:
        return [], "racine inattendue: " + tag
    out = []
    for it in nodes:
        body = text_of(it, "description", "summary", "encoded", "content")
        out.append({
            "title": clean(text_of(it, "title")),
            "url": link_of(it),
            "when": parse_when(text_of(it, "pubDate", "published", "updated",
                                       "date", "created")),
            "summary": clean(body),
            "publisher": (clean(text_of(it, "source", "Source"))
                        or clean(text_of(it, "creator"))),
        })
    return out, None


# ------------------------------------------------------------------- collecte
def resolve_bing(url, timeout=20):
    """Suit la redirection apiclick de Bing jusqu'a l'article d'origine.

    Bing News RSS encapsule les liens dans bing.com/news/apiclick.aspx, mais
    contrairement a Google News il repond par un vrai 302 vers l'editeur.
    """
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": UA,
                                              "Accept-Language": "en-US,en;q=0.9"})
        with op.open(req, timeout=timeout) as r:
            return r.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.headers.get("Location")
    except Exception:
        return None


JINA = "https://r.jina.ai/"
_MON = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
# deux formats rencontres dans le rendu HTML du flux
_DATE_PATS = (
    re.compile(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(20\d\d)"),      # 16 Oct 2026
    re.compile(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(20\d\d)"),      # Oct 16, 2026
)


def find_date(text):
    """Extrait une date d'un fragment de texte, quel que soit le format."""
    for i, rx in enumerate(_DATE_PATS):
        m = rx.search(text)
        if not m:
            continue
        try:
            if i == 0:
                d, mo, y = int(m.group(1)), _MON[m.group(2).lower()[:3]], int(m.group(3))
            else:
                d, mo, y = int(m.group(2)), _MON[m.group(1).lower()[:3]], int(m.group(3))
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except Exception:
            continue
    return None


WP_API = "/wp-json/wp/v2/posts?per_page=20&_fields=title,link,date_gmt,excerpt"


def fetch_wp_api(site, timeout=60, tries=4):
    """Articles via l'API REST WordPress, en UNE requete.

    Bien plus economique que d'ouvrir chaque page d'article (une requete par
    article) et plus fiable : le JSON arrive intact avec date_gmt, donc
    l'horodatage complet. Passe par r.jina.ai en mode texte, seul mode qui
    traverse son rendu sans se faire intercepter par le controle anti-robot
    du site (le mode JSON, lui, tombe sur une page "Robot Challenge Screen").
    """
    api = JINA + site.rstrip("/") + WP_API
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(api, headers={
                "User-Agent": UA, "x-respond-with": "text"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                blob = r.read()
            txt = blob.decode("utf-8", "replace")
            # le controle anti-robot du site renvoie une page, pas du JSON :
            # c'est intermittent, donc on reessaie au lieu d'abandonner.
            if "Robot Challenge" in txt or '[{"' not in txt:
                last = RuntimeError("reponse non-JSON (controle anti-robot)")
                time.sleep(2 + 2 * i)
                continue
            return blob
        except Exception as e:
            last = e
            time.sleep(2 + 2 * i)
    raise last if last else RuntimeError("wp-api indisponible")


def parse_wp_api(blob):
    """Convertit la reponse de l'API REST WordPress en articles."""
    txt = blob.decode("utf-8", "replace").strip()
    start = txt.find("[")
    if start < 0:
        return []
    try:
        data = json.loads(txt[start:])
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for post in data:
        if not isinstance(post, dict):
            continue
        title = ((post.get("title") or {}).get("rendered") or "").strip()
        link = (post.get("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        raw = (post.get("date_gmt") or post.get("date") or "").strip()
        when = parse_when(raw + "Z" if raw and not raw.endswith("Z") else raw)
        exc = clean((post.get("excerpt") or {}).get("rendered") or "")
        for tail in ("[\u2026]", "\u2026", "[...]", "..."):
            if exc.endswith(tail):
                exc = exc[:-len(tail)].strip()
        out.append({"title": clean(title), "url": link, "when": when,
                    "summary": exc, "publisher": "", "author": ""})
    return out


def _via_wpapi(url, site):
    return parse_wp_api(fetch_wp_api(site))


RSS2JSON = "https://api.rss2json.com/v1/api.json?rss_url=%s&count=20"


def fetch_rss2json(url, timeout=45):
    """Convertit un flux RSS en JSON, cote serveur : contourne le blocage d'IP
    tout en PRESERVANT pubDate et description (contrairement au rendu HTML)."""
    req = urllib.request.Request(
        RSS2JSON % urllib.parse.quote(url, safe=""), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_rss2json(blob):
    d = json.loads(blob.decode("utf-8", "replace"))
    if d.get("status") != "ok":
        return []
    out = []
    for it in d.get("items") or []:
        title, link = (it.get("title") or "").strip(), (it.get("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        out.append({"title": clean(title), "url": link,
                    "when": parse_when(it.get("pubDate") or ""),
                    "summary": clean(it.get("description") or ""),
                    "publisher": "", "author": ""})
    return out


def _via_rss2json(url, site):
    for attempt in range(2):
        try:
            got = parse_rss2json(fetch_rss2json(url))
            if got:
                return got
        except Exception:
            pass
        if attempt == 0:
            time.sleep(2)
    return []


def _via_jina(url, site):
    return parse_proxied_items(fetch_via_proxy(url),
                               urllib.parse.urlparse(site).netloc)


def fetch_via_proxy(url, timeout=55):
    """Recours quand l'acces direct est bloque.

    Le filtrage est applicatif et vise l'IP (pas l'User-Agent ni l'empreinte
    TLS : la poignee de main aboutit puis la reponse ne vient jamais). Il frappe
    aussi bien le sandbox que les runners GitHub Actions : verifie sur les deux.

    r.jina.ai est gratuit et sans cle. Il ne renvoie pas le XML brut mais le
    flux rendu en HTML, ou chaque article figure en <h3><a href="...">Titre</a>.
    """
    req = urllib.request.Request(JINA + url, headers={
        "User-Agent": UA, "Accept": "text/html", "x-return-format": "html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_proxied_items(blob, host):
    """Extrait (titre, url, date) d'un flux rendu en HTML par le proxy."""
    h = blob.decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'<h3>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
        url, title = m.group(1).strip(), clean(m.group(2))
        if not title or not url.startswith("http") or host not in url or url in seen:
            continue
        seen.add(url)
        when = (find_date(h[m.end():m.end() + 700])
                or find_date(h[max(0, m.start() - 700):m.start()]))
        out.append({"title": title, "url": url, "when": when,
                    "summary": "", "publisher": "", "author": ""})
    return out


def collect():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DAYS)
    os.makedirs(RAW, exist_ok=True)
    report, staged, proxied = [], [], set()

    # 1. redactions -----------------------------------------------------------
    for name, url, site, mode in RSS_FEEDS:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        path = os.path.join(RAW, slug + ".xml")
        err, blob = None, None
        try:
            blob = fetch(url)
            open(path, "wb").write(blob)
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, getattr(e, "code", e))
        items, perr = ([], "")
        if blob is not None:
            items, perr = parse_xml(path)
        if not items and perr:
            err = ((err or "") + " " + perr).strip()
        # repli : l'acces direct est filtre par IP sur certains sites (verifie
        # dans le sandbox ET sur un runner GitHub Actions).
        #   1. API REST WordPress : 1 requete, horodatage complet
        #   2. rss2json           : horodatage complet (service souvent sature)
        #   3. r.jina.ai          : titres + URL, date au jour pres
        if not items:
            last = ""
            for label, fn in (("wp-api", _via_wpapi),
                              ("rss2json", _via_rss2json),
                              ("jina", _via_jina)):
                try:
                    got = fn(url, site)
                    if got:
                        items, err = got, None
                        proxied.add("%s via %s" % (name, label))
                        break
                except Exception as e2:
                    last = "%s: %s" % (label, type(e2).__name__)
            if not items and last:
                err = ((err or "") + " | " + last).strip()
        n = 0
        for it in items:
            if not it["title"] or not it["url"]:
                continue
            if it["when"] and it["when"] < cutoff:
                continue
            hay = (it["title"] + " " + it["summary"]).lower()
            if mode == "filter" and not any(k in hay for k in KEYWORDS):
                continue
            # publisher = le media (jamais le <dc:creator>, qui est un nom d'auteur :
            # Crossing Broad exposerait sinon "Kevin Kinkead" comme editeur)
            it.update(chip=name, publisher=name, author=it["publisher"], kind="fil",
                      priority=0, site=site)
            it["summary"] = clip(it["summary"])
            it["_dt"] = it["when"] or now
            staged.append(it)
            n += 1
        report.append({"source": name, "site": site, "n": n,
                       "ok": n > 0, "note": (err or "")[:70]})

    # 2. Reddit ---------------------------------------------------------------
    path = os.path.join(RAW, "reddit-phillies.xml")
    err = None
    try:
        open(path, "wb").write(fetch(REDDIT_URL))
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, getattr(e, "code", e))
    items, perr = parse_xml(path) if os.path.exists(path) else ([], "flux absent")
    err = err or perr
    n = 0
    for it in items:
        if not it["title"] or not it["url"] or (it["when"] and it["when"] < cutoff):
            continue
        it.update(chip=REDDIT_NAME, publisher=REDDIT_NAME, kind="reddit",
                  priority=1, site=REDDIT_SITE)
        it["summary"] = clip(it["summary"])
        it["_dt"] = it["when"] or now
        staged.append(it)
        n += 1
    report.append({"source": REDDIT_NAME, "site": REDDIT_SITE, "n": n,
                   "ok": n > 0, "note": (err or "")[:70]})

    # 3. Bing News RSS : liens directs vers les editeurs ---------------------
    resolved = 0
    seen_pub = {}
    for label, query in NEWS_QUERIES:
        url = NEWS_URL % urllib.parse.quote(query)
        path = os.path.join(RAW, "news-%s.xml" % re.sub(r"\W+", "-", label).lower())
        err = None
        try:
            open(path, "wb").write(fetch(url))
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, getattr(e, "code", e))
        items, perr = parse_xml(path) if os.path.exists(path) else ([], "flux absent")
        err = err or perr
        n = 0
        for it in items:
            if not it["title"] or not it["url"]:
                continue
            if it["when"] and it["when"] < cutoff:
                continue
            low = it["title"].lower()
            if "phillies" not in low and "philadelphia" not in low:
                continue
            pub = it["publisher"] or urllib.parse.urlparse(it["url"]).netloc
            if any(j in pub.lower() for j in JUNK_PUBLISHERS):
                continue
            it.update(chip=NEWS_CHIP, publisher=pub, kind="gnews",
                      priority=2, site=NEWS_SITE, summary="",
                      needs_resolve="bing.com" in it["url"])
            it["_dt"] = it["when"] or now
            staged.append(it)
            seen_pub[pub] = seen_pub.get(pub, 0) + 1
            n += 1
        report.append({"source": label, "site": NEWS_SITE, "n": n,
                       "ok": n > 0, "note": (err or "Bing News RSS")[:70]})

    # ---------------------------------------------------------------- dedup
    staged.sort(key=lambda x: (x["priority"], -x["_dt"].timestamp()))
    kept, sigs = [], []
    for it in staged:
        s = tokens(it["title"])
        if any(jac(s, k) >= JACCARD for k in sigs):
            continue
        sigs.append(s)
        kept.append(it)

    # plafonds par source puis global
    per, final = {}, []
    for it in kept:
        c = it["chip"]
        if per.get(c, 0) >= CAPS.get(it["kind"], 14):
            continue
        per[c] = per.get(c, 0) + 1
        final.append(it)
    final.sort(key=lambda x: x["_dt"], reverse=True)
    final = final[:TOTAL_CAP]

    # les liens Bing sont resolus apres selection : ~30 requetes au lieu de 180
    for it in final:
        if it.pop("needs_resolve", False):
            real = resolve_bing(it["url"])
            if real:
                it["url"] = real
                resolved += 1

    items = []
    for it in final:
        items.append({
            "title": it["title"], "url": it["url"],
            "when": it["_dt"].isoformat(), "summary": it["summary"],
            "publisher": it["publisher"], "chip": it["chip"], "site": it["site"],
        })

    payload = {"generated": now.isoformat(), "count": len(items),
               "sources": report, "items": items,
               "publishers": dict(sorted(seen_pub.items(), key=lambda kv: -kv[1])[:12])}

    # garde-fou : ne jamais ecraser un fil correct par une collecte vide
    prev = 0
    if os.path.exists(os.path.join(DATA, "items.json")):
        try:
            prev = json.load(open(os.path.join(DATA, "items.json"),
                                  encoding="utf-8"))["count"]
        except Exception:
            prev = 0
    if not items and prev:
        print("collecte vide -> items.json precedent conserve (%d articles)" % prev)
        return
    json.dump(payload, open(os.path.join(DATA, "items.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("articles retenus: %d" % len(items))
    for r in report:
        print("  %-26s %s n=%-3s %s" % (r["source"], "OK " if r["ok"] else "KO ",
                                        r["n"], r["note"][:52]))
    print("  liens Bing resolus vers l'editeur: %d" % resolved)
    if proxied:
        print("  sources recuperees via proxy gratuit: %s" % ", ".join(sorted(proxied)))
    print("  editeurs via Bing News: %d" % len(seen_pub))
    for p, c in list(sorted(seen_pub.items(), key=lambda kv: -kv[1]))[:8]:
        print("     %-28s %d" % (p[:28], c))


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (utilise dans collect)
    collect()
