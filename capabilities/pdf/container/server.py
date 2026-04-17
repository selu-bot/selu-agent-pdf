"""
Selu Capability Container: PDF Creator

Generates PDF reports from structured text and optional remote images.
"""

import io
import ipaddress
import json
import logging
import re
import signal
import socket
import sys
from datetime import datetime, timezone
from concurrent import futures
from urllib.parse import urlparse
from uuid import uuid4
import base64
from xml.sax.saxutils import escape

import grpc
import requests
import weasyprint
from jinja2 import Template
from PIL import Image as PilImage

import capability_pb2
import capability_pb2_grpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pdf")

GRPC_PORT = 50051
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 4 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 12
MAX_OUTPUT_ARTIFACT_BYTES = 5 * 1024 * 1024

TEMPLATE_REQUIREMENTS = {
    "generic": [],
    "city_profile": [
        ("overview", "ueberblick", "überblick", "einordnung"),
        ("location", "lage", "geografie", "geography"),
        ("highlights", "sehenswuerdigkeiten", "sehenswürdigkeiten", "highlights"),
    ],
    "research_summary": [
        ("scope", "ziel", "objective", "fragestellung"),
        ("findings", "ergebnisse", "key findings", "insights"),
        ("sources", "quellen", "evidence", "references"),
    ],
    "project_status": [
        ("status", "fortschritt", "progress"),
        ("risks", "risiken", "issues", "blocker"),
        ("next steps", "naechste schritte", "nächste schritte", "actions"),
    ],
}

THEMES = {
    "generic": {"accent": "#0f766e", "accent_light": "#ccfbf1", "accent_mid": "#99f6e4"},
    "city_profile": {"accent": "#d97706", "accent_light": "#fef3c7", "accent_mid": "#fde68a"},
    "research_summary": {"accent": "#2563eb", "accent_light": "#dbeafe", "accent_mid": "#93c5fd"},
    "project_status": {"accent": "#4f46e5", "accent_light": "#e0e7ff", "accent_mid": "#a5b4fc"},
}
THEME_DEFAULTS = {"ink": "#0f172a", "muted": "#475569", "soft": "#64748b", "rule": "#cbd5e1"}


def _is_public_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    for info in infos:
        ip_text = info[4][0]
        ip = ipaddress.ip_address(ip_text)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def _validate_image_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https image URLs are allowed")
    if not parsed.hostname:
        raise ValueError("Image URL is missing a hostname")
    if parsed.hostname in {"localhost"}:
        raise ValueError("Localhost image URLs are not allowed")
    if not _is_public_host(parsed.hostname):
        raise ValueError("Image URL host is not publicly routable")
    return url


def _fetch_image(url: str) -> bytes:
    _validate_image_url(url)

    resp = requests.get(
        url,
        stream=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=True,
        headers={"User-Agent": "Selu-PDF-Capability/1.0"},
    )
    resp.raise_for_status()

    # Validate redirect target host as well.
    final_url = resp.url or url
    _validate_image_url(final_url)

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "image" not in content_type:
        raise ValueError("URL does not return an image")

    buf = io.BytesIO()
    size = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        size += len(chunk)
        if size > MAX_IMAGE_BYTES:
            raise ValueError("Image is too large")
        buf.write(chunk)

    # Normalize to a compact RGB JPEG to keep final PDF size reasonable.
    buf.seek(0)
    with PilImage.open(buf) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((1400, 1000))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=78, optimize=True)
        return out.getvalue()


HTML_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
<meta charset="utf-8">
<style>
@page {
  size: A4;
  margin: 2.2cm 2cm 2.4cm 2cm;
  @bottom-left {
    content: "{{ title_short }}";
    font-family: "Inter", sans-serif;
    font-size: 8pt;
    color: {{ muted }};
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;
    max-width: 65%;
  }
  @bottom-right {
    content: "Page " counter(page);
    font-family: "Inter", sans-serif;
    font-size: 8pt;
    color: {{ soft }};
    white-space: nowrap;
  }
  @bottom-center {
    content: "";
    border-top: 0.5pt solid {{ rule }};
    width: 100%;
  }
}
@page :first {
  @bottom-left { content: none; }
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: "Inter", "Helvetica Neue", sans-serif;
  font-size: 10.8pt;
  line-height: 1.55;
  color: {{ ink }};
}
.cover {
  margin-bottom: 1.2em;
}
.cover-bar {
  border-left: 4.5px solid {{ accent }};
  padding-left: 14px;
}
.cover h1 {
  font-size: 26pt;
  font-weight: 700;
  line-height: 1.18;
  color: {{ ink }};
  margin-bottom: 0.15em;
}
.cover .author {
  font-size: 10.5pt;
  font-weight: 600;
  color: {{ accent }};
  margin-bottom: 0.1em;
}
.cover .meta {
  font-size: 9pt;
  color: {{ soft }};
}
.cover .summary {
  font-size: 11pt;
  line-height: 1.6;
  color: {{ muted }};
  margin-top: 0.8em;
}
.cover-image {
  width: 100%;
  max-height: 240px;
  object-fit: cover;
  border-radius: 6px;
  margin-top: 0.9em;
  margin-bottom: 0.2em;
}
section {
  margin-top: 1em;
}
section h2 {
  font-size: 15pt;
  font-weight: 700;
  color: {{ ink }};
  border-left: 3.5px solid {{ accent }};
  padding-left: 10px;
  margin-bottom: 0.45em;
  page-break-after: avoid;
}
p {
  margin-bottom: 0.55em;
  orphans: 3;
  widows: 3;
}
ul, ol {
  margin-left: 1.4em;
  margin-bottom: 0.55em;
}
li {
  margin-bottom: 0.18em;
}
li::marker {
  color: {{ accent }};
}
blockquote {
  background: {{ accent_light }};
  border-left: 3.5px solid {{ accent }};
  border-radius: 0 5px 5px 0;
  padding: 0.65em 0.9em;
  margin: 0.6em 0;
  font-size: 10.5pt;
  color: {{ ink }};
}
blockquote p { margin-bottom: 0.2em; }
strong { font-weight: 700; }
em { font-style: italic; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.6em 0;
  font-size: 10pt;
}
thead th {
  background: {{ accent_light }};
  color: {{ ink }};
  font-weight: 700;
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1.5px solid {{ accent_mid }};
}
tbody td {
  padding: 5px 8px;
  border-bottom: 0.5px solid {{ rule }};
}
tbody tr:nth-child(even) td {
  background: #f8fafc;
}
figure {
  margin: 0.7em 0;
  text-align: center;
  page-break-inside: avoid;
}
figure img {
  max-width: 100%;
  max-height: 320px;
  border-radius: 5px;
}
figcaption {
  font-size: 8.5pt;
  color: {{ soft }};
  margin-top: 0.25em;
}
.sources {
  margin-top: 1.5em;
  padding-top: 0.7em;
  border-top: 0.5px solid {{ rule }};
}
.sources h2 {
  font-size: 11pt;
  font-weight: 700;
  color: {{ muted }};
  border-left: none;
  padding-left: 0;
  margin-bottom: 0.3em;
}
.sources a {
  display: block;
  font-size: 8.8pt;
  color: {{ accent }};
  text-decoration: none;
  margin-bottom: 0.12em;
  word-break: break-all;
}
</style>
</head>
<body>
<div class="cover">
  <div class="cover-bar">
    <h1>{{ title }}</h1>
    {% if author %}<div class="author">{{ author }}</div>{% endif %}
    <div class="meta">{{ generated }}</div>
  </div>
  {% if summary %}<p class="summary">{{ summary }}</p>{% endif %}
  {% if cover_image %}<img class="cover-image" src="{{ cover_image }}" alt="">{% endif %}
</div>
{% for sec in sections %}
<section>
  {% if sec.heading %}<h2>{{ sec.heading }}</h2>{% endif %}
  {{ sec.content_html }}
  {% for img in sec.images %}
  <figure>
    <img src="{{ img.src }}" alt="">
    {% if img.caption %}<figcaption>{{ img.caption }}</figcaption>{% endif %}
  </figure>
  {% endfor %}
</section>
{% endfor %}
{% if source_urls %}
<div class="sources">
  <h2>Sources</h2>
  {% for src in source_urls %}<a href="{{ src }}">{{ src }}</a>{% endfor %}
</div>
{% endif %}
</body>
</html>
""")


def _coerce_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        parts = [_coerce_text(item) for item in value]
        return "\n".join([part for part in parts if part]).strip()
    return ""


def _safe_para_text(value: str) -> str:
    text = _coerce_text(value)
    if not text:
        return ""
    return escape(text, {'"': "&quot;"})


def _extract_urls_from_text(text: str) -> list[str]:
    raw = _coerce_text(text)
    if not raw:
        return []
    seen = set()
    out = []
    for match in re.findall(r"https?://[^\s<>()\"']+", raw, flags=re.IGNORECASE):
        url = match.rstrip(".,);:!?")
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _extract_sources_from_text_fields(summary: str, sections: list[dict[str, str]]) -> list[str]:
    found = []
    seen = set()
    candidates = [summary]
    for section in sections:
        candidates.append(_coerce_text(section.get("content")))
    for text in candidates:
        for url in _extract_urls_from_text(text):
            if url not in seen:
                seen.add(url)
                found.append(url)
    return found


def _clean_block_text(text: str) -> str:
    out = _coerce_text(text)
    if not out:
        return ""
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _looks_like_serialized_sections(text: str) -> bool:
    raw = _coerce_text(text).lower()
    if not raw:
        return False
    if raw.count('"heading"') >= 2 and raw.count('"content"') >= 2:
        return True
    if raw.count('"heading"') >= 1 and raw.startswith("[") and raw.endswith("]"):
        return True
    return False


def _split_content_blocks(content: str) -> list[str]:
    raw = _coerce_text(content)
    if not raw:
        return []
    parts = re.split(r"\n\s*\n", raw)
    return [_coerce_text(p) for p in parts if _coerce_text(p)]


def _parse_list_items(block: str) -> list[str]:
    lines = [_coerce_text(line) for line in _coerce_text(block).splitlines()]
    items = []
    bullet_pattern = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)(.+)$")
    for line in lines:
        if not line:
            continue
        match = bullet_pattern.match(line)
        if not match:
            return []
        item = _clean_block_text(match.group(1))
        if item:
            items.append(item)
    return items


def _parse_markdown_table_block(block: str) -> list[list[str]]:
    lines = [_coerce_text(line) for line in _coerce_text(block).splitlines() if _coerce_text(line)]
    if len(lines) < 2:
        return []
    if not all(line.count("|") >= 2 for line in lines):
        return []

    rows = []
    for line in lines:
        row = [cell.strip() for cell in line.strip("|").split("|")]
        if len(row) < 2:
            return []
        rows.append(row)

    # Markdown table separator row: |---|---| or with alignment markers.
    separator = rows[1]
    if not all(re.fullmatch(r"[:\-\s]+", cell or "") for cell in separator):
        return []

    header_len = len(rows[0])
    normalized = []
    for row in [rows[0]] + rows[2:]:
        padded = row[:header_len] + [""] * max(0, header_len - len(row))
        normalized.append([_clean_block_text(cell) for cell in padded])
    if len(normalized) < 2:
        return []
    return normalized


def _inline_md(text: str) -> str:
    """Convert **bold** and *italic* markers to HTML tags."""
    out = escape(text, {'"': "&quot;"})
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", out)
    return out


def _render_content_html(content: str) -> str:
    """Convert section content (plain text with lists, tables, blockquotes) to HTML."""
    blocks = _split_content_blocks(content)
    if not blocks:
        return ""

    parts = []
    for block in blocks:
        # Markdown table
        table_rows = _parse_markdown_table_block(block)
        if table_rows:
            html = "<table><thead><tr>"
            for cell in table_rows[0]:
                html += f"<th>{_inline_md(cell)}</th>"
            html += "</tr></thead><tbody>"
            for row in table_rows[1:]:
                html += "<tr>"
                for cell in row:
                    html += f"<td>{_inline_md(cell)}</td>"
                html += "</tr>"
            html += "</tbody></table>"
            parts.append(html)
            continue

        # Bullet / numbered list
        list_items = _parse_list_items(block)
        if list_items:
            # Detect numbered vs bullet
            first_line = _coerce_text(block.splitlines()[0]) if block.splitlines() else ""
            is_ordered = bool(re.match(r"^\s*\d+[.)]\s+", first_line))
            tag = "ol" if is_ordered else "ul"
            html = f"<{tag}>"
            for item in list_items:
                html += f"<li>{_inline_md(item)}</li>"
            html += f"</{tag}>"
            parts.append(html)
            continue

        # Blockquote / callout (lines starting with >)
        lines = [_coerce_text(line) for line in block.splitlines() if _coerce_text(line)]
        if lines and all(line.startswith(">") for line in lines):
            quote_lines = [_coerce_text(line.lstrip("> ")) for line in lines]
            inner = " ".join(quote_lines)
            parts.append(f"<blockquote><p>{_inline_md(inner)}</p></blockquote>")
            continue

        # Regular paragraph(s)
        merged = _clean_block_text(" ".join(lines))
        if merged:
            parts.append(f"<p>{_inline_md(merged)}</p>")

    return "\n".join(parts)


def _build_html(
    title: str,
    summary: str,
    author: str,
    sections: list[dict],
    source_urls: list[str],
    template: str,
    cover_image_b64: str | None,
    section_images: dict[int, list[dict]],
) -> str:
    """Render the Jinja2 HTML template with all data."""
    theme_colors = THEMES.get(template, THEMES["generic"])
    generated_dt = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rendered_sections = []
    for idx, sec in enumerate(sections):
        heading = _coerce_text(sec.get("heading"))
        content = _coerce_text(sec.get("content"))
        rendered_sections.append({
            "heading": escape(heading) if heading else "",
            "content_html": _render_content_html(content),
            "images": section_images.get(idx, []),
        })

    safe_sources = []
    if isinstance(source_urls, list):
        for src in source_urls:
            if isinstance(src, str) and src.strip():
                safe_sources.append(escape(src.strip()))

    return HTML_TEMPLATE.render(
        lang="de" if any(
            _coerce_text(s.get("heading")).lower().startswith(kw)
            for s in sections
            for kw in ("lage", "ueber", "über", "sehens", "geschicht", "partner")
        ) else "en",
        title=escape(title),
        title_short=escape(title[:45]),
        author=escape(author) if author else "",
        generated=f"Generated: {generated_dt} UTC",
        summary=_inline_md(summary) if summary else "",
        cover_image=cover_image_b64 or "",
        sections=rendered_sections,
        source_urls=safe_sources,
        accent=theme_colors["accent"],
        accent_light=theme_colors["accent_light"],
        accent_mid=theme_colors["accent_mid"],
        ink=THEME_DEFAULTS["ink"],
        muted=THEME_DEFAULTS["muted"],
        soft=THEME_DEFAULTS["soft"],
        rule=THEME_DEFAULTS["rule"],
    )


def _parse_sections_from_text(text: str) -> list[dict[str, str]]:
    cleaned = _coerce_text(text)
    if not cleaned:
        return []

    # Try extracting JSON sections embedded inside free text first.
    embedded_sections = _extract_sections_from_embedded_json(cleaned)
    if embedded_sections:
        return embedded_sections

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return []

    # Try markdown table first, e.g.:
    # | Abschnitt | Inhalt |
    # |---|---|
    # | Ueberblick | ... |
    table_rows = []
    for line in lines:
        if line.count("|") < 2:
            continue
        row = [cell.strip() for cell in line.strip("|").split("|")]
        if len(row) < 2:
            continue
        if all(re.fullmatch(r"[:\- ]+", cell or "") for cell in row):
            continue
        table_rows.append(row)

    if len(table_rows) >= 2:
        header = [h.lower() for h in table_rows[0]]
        heading_idx = None
        content_idx = None
        for idx, cell in enumerate(header):
            if heading_idx is None and any(
                token in cell for token in ("abschnitt", "section", "heading", "titel", "title")
            ):
                heading_idx = idx
            if content_idx is None and any(
                token in cell for token in ("inhalt", "content", "beschreibung", "details", "text")
            ):
                content_idx = idx
        if heading_idx is None:
            heading_idx = 0
        if content_idx is None:
            content_idx = 1 if len(table_rows[0]) > 1 else 0

        table_sections = []
        for row in table_rows[1:]:
            heading = _coerce_text(row[heading_idx] if heading_idx < len(row) else "")
            content = _coerce_text(row[content_idx] if content_idx < len(row) else "")
            if heading or content:
                table_sections.append({"heading": heading, "content": content})
        if table_sections:
            return table_sections

    # Fallback: parse markdown heading blocks.
    sections = []
    current_heading = ""
    current_content_lines = []

    def flush():
        nonlocal current_heading, current_content_lines
        content = _coerce_text("\n".join(current_content_lines))
        if current_heading or content:
            sections.append({"heading": current_heading, "content": content})
        current_heading = ""
        current_content_lines = []

    for line in lines:
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if match:
            flush()
            current_heading = _coerce_text(match.group(1))
            continue
        current_content_lines.append(line)

    flush()
    if sections:
        return sections

    return [{"heading": "", "content": cleaned}]


def _json_to_sections(value) -> list[dict[str, str]]:
    normalized_sections, _ = _normalize_sections(value)
    return normalized_sections


def _extract_sections_from_embedded_json(text: str) -> list[dict[str, str]]:
    raw = _coerce_text(text)
    if not raw:
        return []

    # Fast path: whole text is JSON.
    if raw[:1] in ("[", "{"):
        try:
            parsed = json.loads(raw)
            sections = _json_to_sections(parsed)
            if sections:
                return sections
        except (json.JSONDecodeError, TypeError):
            pass

    # Slow path: JSON array/object embedded in prose.
    candidates = []
    for opener, closer in (("[", "]"), ("{", "}")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start != -1 and end != -1 and end > start:
            snippet = raw[start : end + 1]
            candidates.append(snippet)

    for snippet in candidates:
        try:
            parsed = json.loads(snippet)
            sections = _json_to_sections(parsed)
            if sections:
                return sections
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: recover from JSON-like blobs that are not strict JSON
    # (common with LLM output: unescaped quotes/newlines inside string values).
    recovered = _extract_sections_from_json_like_blob(raw)
    if recovered:
        return recovered
    return []


def _extract_sections_from_json_like_blob(text: str) -> list[dict[str, str]]:
    raw = _coerce_text(text)
    if not raw:
        return []
    heading_hits = list(
        re.finditer(
            r'"(?:heading|title|name|section|kapitel|thema)"\s*:',
            raw,
            flags=re.IGNORECASE,
        )
    )
    if len(heading_hits) < 2:
        return []

    def _consume_quoted_value(segment: str, start_idx: int) -> tuple[str, int]:
        i = start_idx
        while i < len(segment) and segment[i] in " \t\r\n":
            i += 1
        if i >= len(segment):
            return "", i
        if segment[i] != '"':
            j = i
            while j < len(segment) and segment[j] not in ",}\n":
                j += 1
            return _coerce_text(segment[i:j]), j
        i += 1
        out = []
        while i < len(segment):
            ch = segment[i]
            if ch == "\\" and i + 1 < len(segment):
                out.append(segment[i + 1])
                i += 2
                continue
            if ch == '"':
                # Treat quote as closing only when followed by structural delimiter.
                tail = segment[i + 1 : i + 18]
                if re.match(r"\s*(?:,|\}|$)", tail):
                    i += 1
                    break
            out.append(ch)
            i += 1
        return _coerce_text("".join(out)), i

    sections = []
    for idx, hit in enumerate(heading_hits):
        seg_start = hit.start()
        seg_end = heading_hits[idx + 1].start() if idx + 1 < len(heading_hits) else len(raw)
        segment = raw[seg_start:seg_end]

        heading_match = re.search(
            r'"(?:heading|title|name|section|kapitel|thema)"\s*:\s*',
            segment,
            flags=re.IGNORECASE,
        )
        if not heading_match:
            continue
        heading, pos = _consume_quoted_value(segment, heading_match.end())

        content_match = re.search(
            r'"(?:content|body|text|details|description|inhalt|beschreibung)"\s*:\s*',
            segment[pos:],
            flags=re.IGNORECASE,
        )
        if not content_match:
            continue
        content_start = pos + content_match.end()
        content, _ = _consume_quoted_value(segment, content_start)

        # Remove trailing JSON-ish closure noise.
        content = re.sub(r'"\s*[,}\]]+\s*$', "", content).strip()
        if heading or content:
            sections.append({"heading": heading, "content": content})

    if len(sections) >= 2:
        return sections
    return []


def _recover_sections_from_blob_sections(
    sections: list[dict[str, str]],
) -> tuple[list[dict[str, str]], bool]:
    if not sections:
        return sections, False

    # If a section body accidentally contains serialized JSON sections, recover them.
    for section in sections:
        content = _coerce_text(section.get("content"))
        if not content or ("[" not in content and "{" not in content):
            continue
        recovered = _extract_sections_from_embedded_json(content)
        if len(recovered) >= 2:
            return recovered, True
    return sections, False


def _extract_og_image_urls(source_urls, max_images: int = 3) -> list[str]:
    if not isinstance(source_urls, list):
        return []

    found = []
    seen = set()
    for src in source_urls:
        if not isinstance(src, str) or not src.strip():
            continue
        url = src.strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        try:
            if not _is_public_host(parsed.hostname):
                continue
            resp = requests.get(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
                headers={"User-Agent": "Selu-PDF-Capability/1.0"},
            )
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" not in content_type:
                continue
            html = resp.text or ""
            matches = re.findall(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                flags=re.IGNORECASE,
            )
            for candidate in matches:
                candidate = candidate.strip()
                if not candidate or candidate in seen:
                    continue
                try:
                    _validate_image_url(candidate)
                    found.append(candidate)
                    seen.add(candidate)
                    if len(found) >= max_images:
                        return found
                except Exception:
                    continue
        except Exception:
            continue
    return found


def _heading_has_keyword(heading: str, keyword_group: tuple[str, ...]) -> bool:
    heading_l = _coerce_text(heading).lower()
    if not heading_l:
        return False
    return any(keyword in heading_l for keyword in keyword_group)


def _assess_quality(
    title: str,
    summary: str,
    sections: list[dict[str, str]],
    source_urls,
    template: str,
    require_images: bool,
    image_urls,
) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not _coerce_text(title):
        errors.append("title is empty")

    if not sections:
        errors.append("sections are empty")
    else:
        missing_heading = sum(1 for s in sections if not _coerce_text(s.get("heading")))
        missing_content = sum(1 for s in sections if not _coerce_text(s.get("content")))
        if missing_heading:
            warnings.append(f"{missing_heading} section(s) are missing headings")
        if missing_content:
            errors.append(f"{missing_content} section(s) are missing content")

        total_content_chars = sum(len(_coerce_text(s.get("content"))) for s in sections)
        if total_content_chars < 260:
            warnings.append("overall section content is very short (<260 characters)")

        serialized_blobs = sum(
            1 for s in sections if _looks_like_serialized_sections(_coerce_text(s.get("content")))
        )
        if serialized_blobs:
            errors.append(
                f"{serialized_blobs} section(s) appear to contain serialized section JSON instead of prose"
            )

    if _looks_like_serialized_sections(summary):
        errors.append("summary appears to contain serialized section JSON instead of prose")

    if not isinstance(source_urls, list) or not any(
        isinstance(src, str) and src.strip() for src in source_urls
    ):
        warnings.append("no source_urls provided")
    if require_images and (
        not isinstance(image_urls, list)
        or not any(isinstance(src, str) and src.strip() for src in image_urls)
    ):
        errors.append("require_images=true but no image_urls provided")

    required_heading_groups = TEMPLATE_REQUIREMENTS.get(template, [])
    if required_heading_groups and sections:
        headings = [_coerce_text(s.get("heading")) for s in sections]
        missing_required = []
        for keyword_group in required_heading_groups:
            if not any(_heading_has_keyword(h, keyword_group) for h in headings):
                missing_required.append(keyword_group[0])
        if missing_required:
            errors.append(
                "missing template sections for '%s': %s"
                % (template, ", ".join(missing_required))
            )

    return {"errors": errors, "warnings": warnings}


def _normalize_sections(raw_sections) -> tuple[list[dict[str, str]], dict]:
    stats = {
        "raw_count": 0,
        "non_dict_or_non_text_count": 0,
        "missing_heading_content_count": 0,
        "alias_key_matches": 0,
        "text_sections_derived_count": 0,
    }

    if isinstance(raw_sections, str):
        raw_text = _coerce_text(raw_sections)
        if raw_text:
            # Try parsing JSON string first.
            if raw_text[:1] in ("[", "{"):
                try:
                    raw_sections = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    parsed_from_text = _parse_sections_from_text(raw_text)
                    stats["raw_count"] = 1
                    stats["text_sections_derived_count"] = len(parsed_from_text)
                    return parsed_from_text, stats
            else:
                parsed_from_text = _parse_sections_from_text(raw_text)
                stats["raw_count"] = 1
                stats["text_sections_derived_count"] = len(parsed_from_text)
                return parsed_from_text, stats
        raw_sections = []

    if isinstance(raw_sections, dict):
        if isinstance(raw_sections.get("sections"), list):
            raw_sections = raw_sections["sections"]
        elif isinstance(raw_sections.get("items"), list):
            raw_sections = raw_sections["items"]
        else:
            raw_sections = [
                {"heading": _coerce_text(k), "content": _coerce_text(v)}
                for k, v in raw_sections.items()
            ]
    if not isinstance(raw_sections, list):
        raw_sections = []

    heading_keys = ("heading", "title", "name", "chapter", "section", "kapitel", "thema")
    content_keys = (
        "content",
        "body",
        "text",
        "details",
        "description",
        "inhalt",
        "beschreibung",
    )

    normalized_sections = []
    stats["raw_count"] = len(raw_sections)

    for section in raw_sections:
        heading = ""
        content = ""

        if isinstance(section, dict):
            for key in heading_keys:
                heading = _coerce_text(section.get(key))
                if heading:
                    if key != "heading":
                        stats["alias_key_matches"] += 1
                    break
            for key in content_keys:
                content = _coerce_text(section.get(key))
                if content:
                    if key != "content":
                        stats["alias_key_matches"] += 1
                    break
        else:
            content = _coerce_text(section)
            if not content:
                stats["non_dict_or_non_text_count"] += 1

        if not heading and not content:
            stats["missing_heading_content_count"] += 1
            continue
        normalized_sections.append({"heading": heading, "content": content})

    return normalized_sections, stats


def _build_pdf(args: dict) -> tuple[bytes, dict]:
    title = (args.get("title") or "").strip()
    sections = args.get("sections")
    summary = (args.get("summary") or "").strip()
    author = (args.get("author") or "").strip()
    image_urls = args.get("image_urls") or []
    source_urls = args.get("source_urls") or []
    template = _coerce_text(args.get("template")).lower() or "generic"
    strict_mode = bool(args.get("strict_mode", False))
    require_images = bool(args.get("require_images", False))
    filename = (args.get("filename") or "").strip() or "report.pdf"

    if not title:
        raise ValueError("title is required")
    if template not in TEMPLATE_REQUIREMENTS:
        raise ValueError(
            "template must be one of: %s" % ", ".join(sorted(TEMPLATE_REQUIREMENTS.keys()))
        )
    normalized_sections, section_stats = _normalize_sections(sections)

    # If sections are missing, try extracting blocks from summary text.
    if not normalized_sections and summary:
        summary_sections = _parse_sections_from_text(summary)
        if summary_sections:
            normalized_sections = summary_sections
            section_stats["text_sections_derived_count"] += len(summary_sections)
            summary = ""

    normalized_sections, recovered_from_blob = _recover_sections_from_blob_sections(
        normalized_sections
    )
    if recovered_from_blob:
        section_stats["text_sections_derived_count"] += len(normalized_sections)

    # If we still have a single blob-like section, try extracting embedded JSON once.
    if (
        len(normalized_sections) == 1
        and not _coerce_text(normalized_sections[0].get("heading"))
        and _coerce_text(normalized_sections[0].get("content"))
    ):
        recovered = _extract_sections_from_embedded_json(
            _coerce_text(normalized_sections[0].get("content"))
        )
        if recovered:
            normalized_sections = recovered

    # If we successfully recovered sections from serialized blobs, do not print
    # the raw serialization in summary.
    if summary and _looks_like_serialized_sections(summary) and len(normalized_sections) >= 2:
        summary = ""

    # Be resilient to malformed LLM args: build a minimal report instead of failing.
    if not normalized_sections:
        fallback_content = summary or "This report was generated from your request."
        normalized_sections = [{"heading": "Overview", "content": fallback_content}]
        # Avoid duplicating the same text in summary + section blocks.
        if summary == fallback_content:
            summary = ""
        log.info(
            "sections missing or empty, using fallback section (raw=%s, non_dict_or_non_text=%s, missing_heading_content=%s, alias_key_matches=%s, text_sections_derived=%s)",
            section_stats["raw_count"],
            section_stats["non_dict_or_non_text_count"],
            section_stats["missing_heading_content_count"],
            section_stats["alias_key_matches"],
            section_stats["text_sections_derived_count"],
        )

    if require_images and (
        not isinstance(image_urls, list)
        or not any(isinstance(src, str) and src.strip() for src in image_urls)
    ):
        auto_images = _extract_og_image_urls(source_urls, max_images=3)
        if auto_images:
            image_urls = auto_images

    if not (isinstance(source_urls, list) and any(isinstance(src, str) and src.strip() for src in source_urls)):
        inferred_sources = _extract_sources_from_text_fields(summary, normalized_sections)
        if inferred_sources:
            source_urls = inferred_sources

    quality = _assess_quality(
        title,
        summary,
        normalized_sections,
        source_urls,
        template,
        require_images,
        image_urls,
    )
    if strict_mode and quality["errors"]:
        raise ValueError("quality validation failed: %s" % "; ".join(quality["errors"]))

    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    # --- Fetch images ---
    downloaded_images = []
    image_errors = []
    if isinstance(image_urls, list):
        for idx, image_url in enumerate(image_urls[:MAX_IMAGES]):
            if not isinstance(image_url, str) or not image_url.strip():
                continue
            try:
                data = _fetch_image(image_url.strip())
                downloaded_images.append((image_url.strip(), data))
            except Exception as e:
                image_errors.append(f"image {idx + 1}: {e}")

    if not downloaded_images and require_images and strict_mode:
        image_error_text = "; ".join(image_errors) if image_errors else "no downloadable image"
        raise ValueError(f"quality validation failed: required image missing ({image_error_text})")

    # --- Fetch cover image ---
    cover_image_url = (args.get("cover_image_url") or "").strip()
    cover_image_b64 = None
    if cover_image_url:
        try:
            data = _fetch_image(cover_image_url)
            cover_image_b64 = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        except Exception as e:
            log.warning("cover image failed: %s", e)
    # If no explicit cover image but we have downloaded images, use first as cover.
    if not cover_image_b64 and downloaded_images:
        cover_image_b64 = "data:image/jpeg;base64," + base64.b64encode(downloaded_images[0][1]).decode()

    # --- Distribute remaining images across sections ---
    section_images: dict[int, list[dict]] = {}
    remaining_images = downloaded_images[1:] if cover_image_b64 and downloaded_images else downloaded_images
    if remaining_images and normalized_sections:
        # Spread images evenly across sections (skip first section which is near cover).
        start_idx = min(1, len(normalized_sections) - 1)
        slots = list(range(start_idx, len(normalized_sections)))
        for img_idx, (src_url, img_data) in enumerate(remaining_images):
            sec_idx = slots[img_idx % len(slots)] if slots else 0
            b64 = "data:image/jpeg;base64," + base64.b64encode(img_data).decode()
            section_images.setdefault(sec_idx, []).append({
                "src": b64,
                "caption": escape(src_url),
            })

    # --- Build HTML and render PDF ---
    html = _build_html(
        title=title,
        summary=summary,
        author=author,
        sections=normalized_sections,
        source_urls=source_urls if isinstance(source_urls, list) else [],
        template=template,
        cover_image_b64=cover_image_b64,
        section_images=section_images,
    )
    pdf_bytes = weasyprint.HTML(string=html, base_url="/app/").write_pdf()

    meta = {
        "filename": filename,
        "title": title,
        "template": template,
        "strict_mode": strict_mode,
        "require_images": require_images,
        "sections_count": len(normalized_sections),
        "images_requested": len(image_urls) if isinstance(image_urls, list) else 0,
        "images_added": len(downloaded_images),
        "image_errors": image_errors,
        "quality_errors": quality["errors"],
        "quality_warnings": quality["warnings"],
    }
    return pdf_bytes, meta


class CapabilityServicer(capability_pb2_grpc.CapabilityServicer):
    def __init__(self):
        self._output_artifacts: dict[str, dict] = {}

    def Healthcheck(self, request, context):
        return capability_pb2.HealthResponse(ready=True, message="pdf capability ready")

    def Invoke(self, request, context):
        tool = request.tool_name
        log.info("Invoke tool=%s", tool)

        if tool != "create_pdf_document":
            return capability_pb2.InvokeResponse(error=f"Unknown tool: '{tool}'")

        try:
            args = json.loads(request.args_json) if request.args_json else {}
            pdf_bytes, meta = _build_pdf(args)
            if len(pdf_bytes) > MAX_OUTPUT_ARTIFACT_BYTES:
                return capability_pb2.InvokeResponse(
                    error=(
                        "Generated PDF exceeds size limit "
                        f"({MAX_OUTPUT_ARTIFACT_BYTES} bytes)"
                    )
                )
            capability_artifact_id = str(uuid4())
            self._output_artifacts[capability_artifact_id] = {
                "filename": meta["filename"],
                "mime_type": "application/pdf",
                "data": pdf_bytes,
            }
            result = {
                "ok": True,
                "artifact": {
                    "capability_artifact_id": capability_artifact_id,
                    "filename": meta["filename"],
                    "mime_type": "application/pdf",
                },
                "meta": meta,
            }
            return capability_pb2.InvokeResponse(
                result_json=json.dumps(result).encode("utf-8")
            )
        except Exception as e:
            log.exception("create_pdf_document failed")
            return capability_pb2.InvokeResponse(error=str(e))

    def StreamInvoke(self, request, context):
        resp = self.Invoke(request, context)
        if resp.error:
            yield capability_pb2.InvokeChunk(error=resp.error, done=True)
        else:
            yield capability_pb2.InvokeChunk(data=resp.result_json, done=True)

    def UploadInputArtifact(self, request_iterator, context):
        # PDF capability does not consume input artifacts.
        return capability_pb2.UploadInputArtifactResponse(
            error="UploadInputArtifact is not supported by pdf capability"
        )

    def DownloadOutputArtifact(self, request, context):
        artifact_id = request.capability_artifact_id
        artifact = self._output_artifacts.pop(artifact_id, None)
        if artifact is None:
            yield capability_pb2.ArtifactChunk(
                error=f"Unknown capability_artifact_id: {artifact_id}",
                done=True,
            )
            return

        data = artifact["data"]
        chunk_size = 256 * 1024
        sent = 0
        while sent < len(data):
            end = min(sent + chunk_size, len(data))
            yield capability_pb2.ArtifactChunk(
                data=data[sent:end],
                filename=artifact["filename"] if sent == 0 else "",
                mime_type=artifact["mime_type"] if sent == 0 else "",
                done=end >= len(data),
            )
            sent = end


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    capability_pb2_grpc.add_CapabilityServicer_to_server(CapabilityServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{GRPC_PORT}")
    server.start()
    log.info("PDF capability listening on port %d", GRPC_PORT)

    def _shutdown(signum, frame):
        log.info("Shutting down...")
        server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
