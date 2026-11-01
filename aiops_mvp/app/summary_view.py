"""Turn a summary paragraph into readable parts for the UI: one sentence per line, citations as badges."""

import re

CITE_GROUP = re.compile(r"\s*\[((?:[FIHR]\d+)(?:\s*,\s*[FIHR]\d+)*)\]")
# A sentence ends at . ! ? followed by whitespace; "10:20:03.650" and "0.4%" have no space and stay intact.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=\S)")
BADGE_COLORS = {"F": "blue", "I": "violet", "H": "orange", "R": "red"}


def split_summary(text: str) -> list[tuple[str, list[str]]]:
    """[(sentence without citations, cited IDs in order)]."""
    parts = []
    for sentence in SENTENCE_END.split(text.strip()):
        ids = [i for group in CITE_GROUP.findall(sentence) for i in re.findall(r"[FIHR]\d+", group)]
        clean = CITE_GROUP.sub("", sentence).strip()
        clean = re.sub(r"\s+([.,;:])", r"\1", clean)          # "[F1]." left a space before the dot
        if clean or ids:
            parts.append((clean, list(dict.fromkeys(ids))))
    return parts


def badges(ids: list[str]) -> str:
    return " ".join(f":{BADGE_COLORS[i[0]]}-badge[{i}]" for i in ids)


def escape_markdown(text: str) -> str:
    # `$` would start LaTeX and `[...]`/`*`/`_` could become markup in st.markdown.
    return re.sub(r"([\\`*_\[\]$<>#])", r"\\\1", text)
