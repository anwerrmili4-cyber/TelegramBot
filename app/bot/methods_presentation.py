"""Presentation rules specific to the single-unit Methods catalog."""

from __future__ import annotations

import html
import re

from app.bot.presentation import render_stored_rich_text

_METHOD_HIDDEN_DETAIL_LABELS = (
    "duration", "period", "warranty", "stock",
    "durée", "duree", "période", "periode", "garantie",
    "المدة", "الفترة", "الضمان", "المخزون",
)
_DESCRIPTION_LABEL_RE = re.compile(r"^(?:description|الوصف)\s*:?\s*$", re.IGNORECASE)
_BMC_DURATION_WORD = (
    r"days?|day|j|jours?|mois|months?|ans?|years?|ann[eé]es?|an|"
    r"يوم|أيام|شهر|أشهر|اشهر|سنة|سنوات"
)
_BMC_TERM_VALUE = rf"(?:NW|FW|\d+\s*(?:{_BMC_DURATION_WORD}))"


def is_method_detail_row(line):
    """Recognize detail rows even when their icon is a Premium emoji tag."""
    visible = html.unescape(re.sub(r"<[^>]+>", "", str(line or ""))).strip()
    visible = re.sub(
        r"^[^0-9A-Za-zÀ-ÖØ-öø-ÿ\u0600-\u06ff]+", "", visible,
    ).casefold()
    return any(
        visible == label
        or visible.startswith(f"{label}:")
        or visible.startswith(f"{label} :")
        for label in _METHOD_HIDDEN_DETAIL_LABELS
    )


def without_method_detail_rows(text):
    """Remove duration, warranty and stock rows from a Methods message/card."""
    return "\n".join(
        line for line in str(text or "").splitlines()
        if not is_method_detail_row(line)
    ).strip()


def visible_message_line(line):
    visible = html.unescape(re.sub(r"<[^>]+>", "", str(line or ""))).strip()
    return re.sub(
        r"^[^0-9A-Za-zÀ-ÖØ-öø-ÿ\u0600-\u06ff]+", "", visible,
    ).strip()


def line_is_description_label(line):
    """Return whether a Methods line is only the Description label."""
    return bool(_DESCRIPTION_LABEL_RE.match(visible_message_line(line)))


def line_opens_blockquote(line):
    return bool(re.match(r"\s*<blockquote\b", str(line or ""), re.I))


def join_methods_description_title(text):
    """Put the Description label and its opening text on the same line."""
    lines = str(text or "").splitlines()
    joined = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line_is_description_label(line):
            follower = index + 1
            while follower < len(lines) and not lines[follower].strip():
                follower += 1
            if follower < len(lines) and not line_opens_blockquote(lines[follower]):
                line = f"{line.rstrip()} {lines[follower].strip()}"
                index = follower
        joined.append(line)
        index += 1
    return "\n".join(joined)


def split_description_title(description):
    """Keep the first description line with the label and the list below it."""
    description = str(description or "").strip()
    if not description:
        return "", ""
    block = re.search(r"<blockquote\b", description, re.I)
    if block and block.start() == 0:
        return "", description
    if block:
        head = description[:block.start()].strip()
        tail = description[block.start():].strip()
    else:
        head, separator, tail = description.partition("\n")
        head = head.strip()
        tail = tail.strip() if separator else ""
    return re.sub(r"\s+", " ", head), tail


def methods_description_row(lang, description):
    """Build a one-line Methods description title and optional product list."""
    label = {"fr": "Description", "ar": "الوصف"}.get(lang, "Description")
    label_html = f"💬 <b>{label}:</b>"
    head, tail = split_description_title(description)
    if head:
        row = f"{label_html} {head}"
        return f"{row}\n{tail}" if tail else row
    if tail:
        return f"{label_html}\n{tail}"
    return ""


def is_bmc_vip_product(offer):
    offer = offer or {}
    if str(offer.get("feature_key") or "") == "bmc_vip":
        return True
    return str(offer.get("name") or "").strip().casefold() == "bmc vip"


def _wrapped_bmc_term(group):
    return (
        rf"\s*\|\s*(?:<(?P<{group}>[A-Za-z][\w-]*)\b[^>]*>\s*)?"
        rf"{_BMC_TERM_VALUE}"
        rf"(?({group})\s*</(?P={group})>)"
    )


_BMC_VIP_TERM_SUFFIX = re.compile(
    _wrapped_bmc_term("tag_a") + _wrapped_bmc_term("tag_b"),
    re.IGNORECASE,
)


def strip_bmc_vip_term_suffix(text):
    """Remove a ``| 30 days | NW`` suffix from the BMC VIP title only."""
    return "\n".join(
        _BMC_VIP_TERM_SUFFIX.sub("", line)
        if "bmc vip" in visible_message_line(line).casefold()
        else line
        for line in str(text or "").splitlines()
    )


def method_announcement_description(value):
    """Render a method description without exposing stored HTML source."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("[[HTML]]", "[HTML]", "[[TGEMOJI:")):
        rendered = render_stored_rich_text(raw, parse_legacy_markdown=False)
    else:
        cleaned = re.sub(r"</?[^>]+>", "", raw)
        rendered = render_stored_rich_text(cleaned, parse_legacy_markdown=False)
    return re.sub(
        r"</?(?:code|pre)(?:\s[^>]*)?>", "", rendered, flags=re.I,
    ).strip()


def method_announcement_text(text, service, offer=None, lang="en"):
    """Replace period, warranty, and stock rows with the method description."""
    if str((service or {}).get("name") or "").strip().casefold() != "methods":
        return text
    raw_description = (
        (offer or {}).get("description_ar")
        if lang == "ar" and (offer or {}).get("description_ar")
        else (offer or {}).get("description")
    )
    description = method_announcement_description(raw_description)
    description_row = methods_description_row(lang, description)
    head, tail = split_description_title(description)
    head_visible = html.unescape(re.sub(r"<[^>]+>", "", head)).strip()
    visible_text = html.unescape(re.sub(r"<[^>]+>", "", str(text or "")))
    inserted = bool(head_visible) and head_visible in visible_text
    rows = []
    for line in str(text or "").splitlines():
        if is_method_detail_row(line):
            if description_row and not inserted:
                rows.extend(description_row.splitlines())
                inserted = True
            continue
        if description_row and not inserted and line_is_description_label(line):
            rows.extend(description_row.splitlines())
            inserted = True
            continue
        rows.append(line)
    if description_row and not inserted:
        rows.extend(description_row.splitlines())
    rendered = join_methods_description_title("\n".join(rows))
    if tail and tail not in rendered:
        rendered = f"{rendered.rstrip()}\n{tail}"
    if is_bmc_vip_product(offer):
        rendered = strip_bmc_vip_term_suffix(rendered)
    return rendered


__all__ = [
    "is_bmc_vip_product",
    "is_method_detail_row",
    "join_methods_description_title",
    "line_is_description_label",
    "line_opens_blockquote",
    "method_announcement_description",
    "method_announcement_text",
    "methods_description_row",
    "split_description_title",
    "strip_bmc_vip_term_suffix",
    "visible_message_line",
    "without_method_detail_rows",
]
