"""Live look-ups on the public BIS sites: foreign licensees (FMCS list) and approved labs (LIMS)."""

import datetime
import html
import re
from concurrent.futures import ThreadPoolExecutor

import requests

FMCS_URL = "https://www.services.bis.gov.in/php/BIS_2.0/fmcs/All_fmcs_list.php"
LIMS_URL = "https://lims.bis.gov.in/home/search_labs/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SunConsultantsQuotationTool)"}
TIMEOUT = 15
MAX_LABS = 10
MANUAL_LIST_URL = "https://standardsadmin.bis.gov.in/review-service//getProductManualStandardsList"
MANUAL_FILES_URL = "https://bmqsdqljvwgm.compat.objectstorage.ap-mumbai-1.oraclecloud.com/"
MANUAL_HEADERS = dict(HEADERS, **{"Content-Type": "application/json", "Origin": "https://standards.bis.gov.in",
                                  "Referer": "https://standards.bis.gov.in/"})


def _rows(page_html):
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if cells:
            rows.append(cells)
    return rows


def fmcs_count(is_number):
    """Number of operative foreign (FMCS) licences for an IS number, or raises."""
    number = re.sub(r"\D", "", is_number.split("(")[0])
    resp = requests.post(FMCS_URL, data={"country": "0", "is_search": number, "search": "search"},
                         headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    pattern = re.compile(rf"\bIS\s*{number}\b", re.I)
    licences = set()
    for cells in _rows(resp.text)[1:]:
        if len(cells) >= 6 and pattern.search(cells[4]) and cells[5].strip().lower() == "operative":
            licences.add(cells[1])
    return len(licences)


def _clean_lab(name):
    # internal lab codes such as (27), (D115A), (C-54), (6126126); "(Unit-2)" and "(India)" stay
    name = re.sub(r"\s*\((?=[A-Z0-9\-]*\d)[A-Z0-9\-]{1,10}\)", "", name)
    return re.sub(r"\s+", " ", name).strip(" ,")


def labs_for(is_number):
    """Names of BIS labs listed for an IS number (expired validity dates are left out)."""
    number = re.sub(r"\D", "", is_number.split("(")[0])
    resp = requests.get(LIMS_URL, params={"lab_name": "", "lab_is_number": number, "lab_state": "",
                                          "lab_district": "", "lab_type": ""},
                        headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    today = datetime.date.today()
    names = []
    for cells in _rows(resp.text)[1:]:
        if len(cells) < 8:
            continue
        validity = cells[7]
        try:
            if datetime.datetime.strptime(validity, "%d %b, %Y").date() < today:
                continue
        except ValueError:
            pass                                        # "-" : no date shown, keep the lab
        name = _clean_lab(cells[2])
        if name and name not in names:
            names.append(name)
    return names


def allocate_labs(labs_by_is, limit=MAX_LABS):
    """Pick at most `limit` labs for the slide.

    Labs approved for every standard come first; the remaining places are shared out
    between the standards in equal parts (extra places go to the later standards,
    e.g. 3-3-4 for three standards). Returns (names, more_exist).
    """
    order = list(labs_by_is)
    if not order:
        return [], False
    everything = []
    for k in order:
        for lab in labs_by_is[k]:
            if lab not in everything:
                everything.append(lab)

    picked = []
    if len(order) > 1:
        picked = [lab for lab in labs_by_is[order[0]]
                  if all(lab in labs_by_is[k] for k in order[1:])][:limit]
    n = len(order)
    base, extra = divmod(limit - len(picked), n)
    quota = [base + (1 if i >= n - extra else 0) for i in range(n)]
    for i, k in enumerate(order):
        for lab in labs_by_is[k]:
            if quota[i] <= 0:
                break
            if lab not in picked:
                picked.append(lab)
                quota[i] -= 1
    for lab in everything:                              # a standard had too few labs: fill the gap
        if len(picked) >= limit:
            break
        if lab not in picked:
            picked.append(lab)
    return picked, len(everything) > len(picked)


def _manual_title(number):
    row = find_manual(number)
    return row["standardName"] if row else ""


def lookup(is_numbers):
    """Run all look-ups in parallel. Returns {'fmcs': {...}, 'labs_by_is': {...}, 'errors': [...]}."""
    result = {"fmcs": {}, "labs_by_is": {}, "manuals": {}, "errors": []}

    def one(number):
        out = {"number": number, "fmcs": None, "labs": None, "manual": None}
        for key, func in (("fmcs", fmcs_count), ("labs", labs_for), ("manual", _manual_title)):
            try:
                out[key] = func(number)
            except Exception:
                out[key] = None
        return out

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(is_numbers)))) as pool:
        for out in pool.map(one, is_numbers):
            if out["fmcs"] is None:
                result["errors"].append(f"Could not read the foreign licensee count for IS {out['number']}. Please type it.")
            else:
                result["fmcs"][out["number"]] = out["fmcs"]
            result["manuals"][out["number"]] = out["manual"] or None
            if out["labs"] is None:
                result["errors"].append(f"Could not read the labs list for IS {out['number']}. Please type the labs.")
            else:
                result["labs_by_is"][out["number"]] = out["labs"]
    return result


# ---------------- product manuals (standards.bis.gov.in/website/product-manuals) ----------------

def _compact(text):
    return re.sub(r"\s+", "", text or "").upper()


def find_manual(is_number):
    """Entry of the BIS product-manual list for this exact IS number, or None."""
    number = _compact(is_number)
    body = {"searchTerm": re.sub(r"\D", "", is_number.split("(")[0]), "page": 1, "per_page": 50,
            "sortBy": "committee", "sortOrder": "asc", "token": None, "refreshToken": None,
            "clientId": None, "clientSecret": None, "sub": None}
    resp = requests.post(MANUAL_LIST_URL, json=body, headers=MANUAL_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    hits = [row for row in resp.json().get("data", [])
            if _compact(row.get("standardNumber")).startswith("IS" + number + ":") and row.get("filename")]
    if not hits:
        return None
    return sorted(hits, key=lambda row: row["standardNumber"])[-1]       # latest year if there are several


def download_manual(is_number):
    """PDF bytes of the product manual, or None if BIS has no manual for this standard."""
    row = find_manual(is_number)
    if not row or not row["filename"].startswith("BisProd/"):
        return None
    resp = requests.get(MANUAL_FILES_URL + row["filename"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content if resp.content[:5] == b"%PDF-" else None


def fetch_manuals(is_numbers):
    """{number: pdf bytes or None} for several standards, downloaded in parallel."""
    def one(number):
        try:
            return download_manual(number)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(is_numbers)))) as pool:
        return dict(zip(is_numbers, pool.map(one, is_numbers)))
