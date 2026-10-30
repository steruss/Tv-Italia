"""Crea epg.json: per ogni canale nazionale della lista, i programmi delle prossime ore.
Gira su GitHub Actions ogni 3 ore. Usa solo la libreria standard di Python."""
import gzip, json, re, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

PLAYLIST = "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_italy.m3u8"
EPG = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"
HOURS = 12  # quante ore di programmi tenere

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 tv-italia"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def norm(s):
    s = s.lower().replace("+", "plus")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\s{2,}\d{2,}\s*$", "", s.strip())   # "NOVE HD  149" -> "NOVE HD"
    s = re.sub(r"\b(hd|it|italia\b(?=.*\d))\b", "", s)
    s = re.sub(r"\.\.\d+", "", s)          # "Rai.1.HD..101.it" -> numero canale Sky
    s = re.sub(r"[^a-z0-9]", "", s)
    return s.replace("hd", "") if s not in ("hgtv",) else s

def ptime(t):
    return datetime.strptime(t[:20].strip(), "%Y%m%d%H%M%S %z")

# 1) canali nazionali della lista (prima di quelli senza numero)
names = []
for line in get(PLAYLIST).decode("utf-8", "replace").splitlines():
    if not line.startswith("#EXTINF"):
        continue
    if "tvg-chno=" not in line:
        break
    m = re.search(r'tvg-name="([^"]*)"', line)
    name = re.sub(r"[ⒼⓈⓎ]", "", m.group(1) if m else line.split(",")[-1]).strip()
    if name not in names:
        names.append(name)

# 2) guida TV
root = ET.fromstring(gzip.decompress(get(EPG)))
idx = {}  # nome normalizzato -> tutti gli id canale EPG con quel nome
for ch in root.findall("channel"):
    cid = ch.get("id")
    for key in {norm(cid)} | {norm(d.text or "") for d in ch.findall("display-name")}:
        idx.setdefault(key, []).append(cid)

alias = {"la7": ["la7"], "tv8": ["tv8"], "20mediaset": ["20"], "27twentyseven": ["27twentyseven", "twentyseven"],
         "la7cinema": ["la7cinema", "la7d"], "cine34": ["cine34"], "boing": ["boing"], "tv2000": ["tv2000"],
         "giallo": ["giallotv"], "tgcom24": ["tgcom"], "hgtvhomegardentv": ["hgtv"]}
want = {}
for n in names:
    k = norm(n)
    for cand in [k] + alias.get(k, []):
        if cand in idx:
            for cid in idx[cand]:
                want[cid] = n
            break

now = datetime.now(timezone.utc)
end = now + timedelta(hours=HOURS)
byid = {}
for p in root.findall("programme"):
    cid = p.get("channel")
    name = want.get(cid)
    if not name:
        continue
    try:
        a, b = ptime(p.get("start")), ptime(p.get("stop"))
    except Exception:
        continue
    if b <= now or a >= end:
        continue
    title = (p.findtext("title") or "").strip()
    byid.setdefault((name, cid), []).append([int(a.timestamp()), int(b.timestamp()), title])

# se un canale ha più fonti, tiene quella con più programmi
out = {}
for (name, cid), progs in byid.items():
    if len(progs) > len(out.get(name, [])):
        out[name] = sorted(progs)
missing = [n for n in names if n not in out]
json.dump({"updated": int(now.timestamp()), "channels": out}, open("epg.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"canali con guida: {len(out)} su {len(names)}")
print("senza guida:", ", ".join(missing))
