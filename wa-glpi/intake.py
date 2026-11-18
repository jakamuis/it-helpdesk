"""Parse requester-provided ticket fields without waiting for the triage model."""
import re

GREETING_PREFIX = re.compile(
    r"^(?:halo|hallo|hai|pagi|siang|sore|malam|selamat pagi|selamat siang|selamat sore|selamat malam)[\s,!👋]+", re.I
)

SITE = r"(?:SIG|SGI|HO(?:[ -]?[1-9])?|Arohera)\s+[\w]+(?:\s+[\w]+){0,3}"
LOCATION = re.compile(rf"\b(?:di|lokasi[: ]+|cabang[: ]+)\s*(?:kantor\s+)?({SITE}|HO)\b", re.I)
NAME_WORD = r"[^\W\d_]+(?:[.'’-][^\W\d_]+)*"
NAME = re.compile(rf"{NAME_WORD}(?:\s+{NAME_WORD}){{0,3}}", re.UNICODE)
INTRODUCTION = re.compile(
    rf"(?:\bnama saya\s+|\bnama\s*:\s*|^saya\s+)({NAME_WORD}(?:\s+{NAME_WORD}){{0,3}}?)"
    r"(?=\s+(?:di|dari|lokasi|cabang|mau|ingin|butuh|mengalami)\b|[.,;\n]|$)", re.I
)
ISSUE_WORDS = re.compile(
    r"\b(?:internet|wifi|printer|laptop|komputer|rusak|macet|lambat|error|kendala|tolong|mohon|"
    r"bantu|install|instal|tidak|gagal|akses|down|problem|reset|cek|masih|sudah|terima|kasih|pabrik|mati|total|belum|masalah|butuh|ingin|mau|vpn|email|password|layanan)\b", re.I
)
INSTALL = re.compile(r"\b(?:install|instal(?:asi)?)\s+(.+?)(?=\s+PO\b|$)", re.I)


def valid_name(value):
    value = str(value or "").strip()
    if (NAME.fullmatch(value) and value.casefold() not in {
        "unknown user", "unknown", "whatsapp", "user", "admin", "tidak diketahui",
    }):
        return value
    return ""


def branch(value):
    value = " ".join(value.split())
    head, space, rest = value.partition(" ")
    if head.upper() in {"SIG", "SGI", "HO"}:
        return head.upper() + space + rest
    return value


def identity_only(message):
    text = GREETING_PREFIX.sub("", message.strip()).rstrip(".!")
    name, separator, site = text.partition(" - ")
    if separator and valid_name(name) and re.fullmatch(rf"(?:{SITE}|HO)", site, re.I):
        return {"name": name, "site": branch(site)}
    if re.fullmatch(rf"(?:{SITE}|HO)", text, re.I):
        return {"site": branch(text)}
    if ISSUE_WORDS.search(text):
        return {}
    name_match = INTRODUCTION.search(text)
    location = LOCATION.search(text)
    spans = sorted(filter(None, (name_match, location)), key=lambda match: match.start())
    if spans and spans[0].start() == 0 and spans[-1].end() == len(text):
        fields = {}
        if name_match and valid_name(name_match[1]):
            fields["name"] = valid_name(name_match[1])
        if location:
            fields["site"] = branch(location[1])
        return fields
    if valid_name(text):
        return {"name": text}
    return {}


def extract(message, profile, previous=None):
    parts = re.split(r"\s+-\s+", message.strip(), maxsplit=2)
    if len(parts) == 3 and valid_name(parts[0]):
        return {"name": valid_name(parts[0]), "site": branch(parts[1]),
                "summary": previous["summary"] if previous else parts[2].strip()[:160]}

    text = GREETING_PREFIX.sub("", message.strip())
    name_match = INTRODUCTION.search(text)
    site_match = LOCATION.search(text)
    name = valid_name(name_match[1]) if name_match else ""
    if ISSUE_WORDS.search(name):
        name_match = None
        name = ""
    site = branch(site_match[1]) if site_match else ""
    if not site:
        site_label = re.search(r"\b(?:lokasi|cabang)\s*:\s*([^,.;\n]+)", text, re.I)
        if site_label:
            site_match = site_label
            site = branch(site_label[1])

    if previous:
        identity = identity_only(text)
        name = name or (identity.get("name", "") if not previous["name"] else "")
        site = site or identity.get("site", "")
        if not site and re.fullmatch(rf"(?:{SITE}|HO)[.!]?", text, re.I):
            site = branch(text.rstrip(".!"))
        return {**previous, "name": name or previous["name"] or valid_name(profile),
                "site": site or previous["site"]}

    summary = text
    for match in sorted(filter(None, (name_match, site_match)), key=lambda m: m.start(), reverse=True):
        summary = summary[:match.start()] + summary[match.end():]
    summary = " ".join(summary.strip(" .,:;-").split())
    install = INSTALL.search(summary)
    if install:
        summary = "Permintaan instalasi " + install[1].strip(" .,:;-")
    else:
        summary = re.split(r"\bPO\s+\d", summary, maxsplit=1, flags=re.I)[0].rstrip(" .,:;-")
    return {"name": name or valid_name(profile), "site": site, "summary": (summary or text)[:160]}


def title(fields):
    name = (fields["name"] or "Pelapor belum diketahui")[:65]
    site = (fields["site"] or "Cabang belum diketahui").replace(" - ", " – ")[:65]
    return f"{name} - {site} - {fields['summary'][:119]}"


def confirmation(ticket_id, fields):
    reply = f"Laporan Anda sudah dicatat dengan nomor tiket #{ticket_id}."
    if not fields["name"] and not fields["site"]:
        return reply + "\nBoleh sebutkan nama Anda dan cabang atau lokasi yang terdampak?"
    if not fields["name"]:
        return reply + "\nBoleh sebutkan nama Anda?"
    if not fields["site"]:
        return reply + "\nBoleh sebutkan cabang atau lokasi yang terdampak?"
    return reply
