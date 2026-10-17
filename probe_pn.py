"""Sonde : acces a Phillies Nation depuis l'IP du runner GitHub."""
import urllib.request, time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
URL = "https://philliesnation.com/feed/"


def get(u, timeout=25):
    return urllib.request.urlopen(urllib.request.Request(u, headers={
        "User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity"}),
        timeout=timeout)


print("=== 1. ACCES DIRECT ===", flush=True)
for i in range(3):
    try:
        with get(URL) as r:
            b = r.read()
        print("  essai %d : OK %d octets | %r" % (i + 1, len(b), b[:70]), flush=True)
        break
    except Exception as e:
        print("  essai %d : %s | %s" % (i + 1, type(e).__name__, str(e)[:70]), flush=True)
    time.sleep(2)

print("=== 2. PROXYS PUBLICS GRATUITS ===", flush=True)
for name, base in [("allorigins", "https://api.allorigins.win/raw?url="),
                   ("codetabs", "https://api.codetabs.com/v1/proxy?quest="),
                   ("r.jina.ai", "https://r.jina.ai/")]:
    try:
        with get(base + URL, timeout=45) as r:
            b = r.read(200)
        print("  %-11s OK %r" % (name, b[:70]), flush=True)
    except Exception as e:
        print("  %-11s %s | %s" % (name, type(e).__name__, str(e)[:60]), flush=True)
