from googleapiclient.discovery import build
import os, sys, re, tempfile
import requests
from io import BytesIO
from PIL import Image
from urllib.parse import urlparse

API_KEY = "AIzaSyDswDhLoXmkJ6PusnVSWz2N19eoiT9WZgw"
CSE_ID = "c72204955425844de"

# High-quality food sites
DOMAINS = [
    "seriouseats.com","bonappetit.com","epicurious.com","bbcgoodfood.com",
    "allrecipes.com","foodnetwork.com","tasteatlas.com","justonecookbook.com",
    "thespruceeats.com","foodgawker.com",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Terms to exclude when we expect a savory dish (e.g., burger)
NEG_SWEET = {"dessert","tart","pie","cake","brownie","cookie","pudding","fruit","sweet","mousse","cheesecake","galette","cobbler"}
# Optional global negatives that often cause junk
NEG_GENERIC = {"logo","vector","illustration","clipart","packaging","stock","getty","shutterstock","alamy"}

def normalize_menu_item(raw: str):
    """Turn a messy menu line into (core, modifiers)"""
    s = raw.strip().lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"\b\d+(?:\.\d+)?\s?(?:g|kg|oz|ml|l|cm|mm|in|inch|€|\$)\b", " ", s)  # 180g, 12 oz, 12€
    s = re.sub(r"[(),/]|{", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    tokens = s.split()

    # very small heuristic for burgers
    if "burger" in tokens or "cheeseburger" in tokens or "hamburger" in tokens:
        core = "cheeseburger" if ("cheddar" in tokens or "cheese" in tokens or "cheeseburger" in tokens) else ("hamburger" if "hamburger" in tokens else "burger")
    else:
        core = tokens[0]

    stop = {core, "burger","cheeseburger","hamburger","with","and","the","a","an","of"}
    mods = [t for t in tokens if t not in stop]
    # prioritize helpful words
    priority = {"beef":3,"chicken":3,"pork":3,"cheddar":2,"cheese":2,"tomato":1,"onion":1,"lettuce":1,"pickles":1}
    mods = sorted(mods, key=lambda t: priority.get(t,0), reverse=True)[:3]
    return core, mods

def build_q(core, mods, add_context=True, use_negatives=True):
    parts = [core]
    # light synonyms for burgers
    if core in {"burger","hamburger","cheeseburger"}:
        parts.append('(hamburger OR "beef burger" OR cheeseburger)')
    parts += mods
    if add_context:
        parts += ['"restaurant"', '"plated"']
    if use_negatives:
        parts += [f'-"{t}"' for t in NEG_GENERIC]
    return " ".join(parts)

def cse_image_search(q, domain, num=3, img_type="photo", safe="active"):
    """Search a single domain using siteSearch to force coverage."""
    service = build("customsearch", "v1", developerKey=API_KEY)
    res = service.cse().list(
        q=q, cx=CSE_ID, searchType="image", num=min(10, num), safe=safe,
        imgType=img_type, siteSearch=domain, siteSearchFilter="i"
    ).execute()
    return res.get("items", [])

def is_relevant(item, core_keywords, savory=True):
    """Filter obvious mismatches using URL, title/snippet, and negatives."""
    title = (item.get("title") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    url = (item.get("link") or "").lower()

    text = " ".join([title, snippet, url])
    # require at least one core keyword in either title/snippet/url
    if not any(k in text for k in core_keywords):
        return False
    # if savory dish, avoid dessert-y terms
    if savory and any(term in text for term in NEG_SWEET):
        return False
    return True

def canonical_image_id(url):
    """De-dup by stripping query params and normalizing path."""
    try:
        u = urlparse(url)
        path = u.path.lower()
        # keep filename without query params
        return f"{u.netloc.lower()}{path}"
    except Exception:
        return url

def fetch_image_bytes(url, thumbnail_url=None):
    headers_sets = [
        {"User-Agent": UA, "Referer": f"https://{urlparse(url).netloc}/"},
        {"User-Agent": UA, "Referer": "https://www.google.com/"},
        {"User-Agent": UA},
    ]
    for headers in headers_sets:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r.content
        except Exception:
            pass
    if thumbnail_url:
        try:
            r = requests.get(thumbnail_url, headers={"User-Agent": UA, "Referer": "https://www.google.com/"}, timeout=20)
            r.raise_for_status()
            return r.content
        except Exception:
            pass
    return None

def save_and_open(images, max_to_open=2):
    if not images:
        print("No images to open.")
        return
    out_dir = os.path.join(tempfile.gettempdir(), "dish_images")
    os.makedirs(out_dir, exist_ok=True)
    opened = 0
    for it in images:
        if opened >= max_to_open:
            break
        full = it.get("link")
        thumb = (it.get("image") or {}).get("thumbnailLink")
        raw = fetch_image_bytes(full, thumb)
        if not raw:
            continue
        try:
            img = Image.open(BytesIO(raw))
            ext = (img.format or "JPEG").lower()
            if ext == "jpeg": ext = "jpg"
            path = os.path.join(out_dir, f"result_{opened+1}.{ext}")
            img.save(path)
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess; subprocess.run(["open", path], check=False)
            else:
                import subprocess; subprocess.run(["xdg-open", path], check=False)
            print("Opened:", path)
            opened += 1
        except Exception as e:
            print("Open failed:", e)

def get_diverse_images(raw_query, per_site=2, want=4):
    core, mods = normalize_menu_item(raw_query)
    print("Parsed:", {"core": core, "modifiers": mods})

    # Build a reasonable base query
    q_primary = build_q(core, mods, add_context=True, use_negatives=True)
    q_looser  = build_q(core, mods, add_context=False, use_negatives=False)

    # keywords to verify relevance
    core_keywords = {core, "burger", "cheeseburger", "hamburger"} if "burger" in core or core == "cheeseburger" else {core}

    seen_images, seen_pages = set(), set()
    results = []

    # pass 1: stricter query per site
    for domain in DOMAINS:
        items = cse_image_search(q_primary, domain, num=per_site)
        for it in items:
            link = it.get("link") or ""
            ctx  = (it.get("image") or {}).get("contextLink","")
            if canonical_image_id(link) in seen_images or ctx in seen_pages:
                continue
            if not is_relevant(it, core_keywords, savory=True):
                continue
            seen_images.add(canonical_image_id(link)); seen_pages.add(ctx)
            results.append(it)
            if len(results) >= want:
                return results

    # pass 2: looser query per site (to fill gaps)
    for domain in DOMAINS:
        items = cse_image_search(q_looser, domain, num=per_site, img_type=None)
        for it in items:
            link = it.get("link") or ""
            ctx  = (it.get("image") or {}).get("contextLink","")
            if canonical_image_id(link) in seen_images or ctx in seen_pages:
                continue
            if not is_relevant(it, core_keywords, savory=True):
                continue
            seen_images.add(canonical_image_id(link)); seen_pages.add(ctx)
            results.append(it)
            if len(results) >= want:
                return results
    return results

if __name__ == "__main__":
    query = "cheeseburger-180g-beef-cheddar"
    items = get_diverse_images(query, per_site=2, want=4)
    print(f"Collected {len(items)} images from {len({(it.get('image') or {}).get('contextLink','') for it in items})} pages.")
    for i, it in enumerate(items, 1):
        print(f"{i}. {it.get('link')}  (from {it.get('displayLink')})")
    save_and_open(items, max_to_open=2)

