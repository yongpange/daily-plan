"""富文本工具：感悟内容的 HTML 清洗、纯文本提取与长度校验。"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from .errors import AppError

_RICH_TAGS = {"p", "br", "strong", "b", "ul", "ol", "li", "h3", "div"}
_RICH_SIZE = {"note-lg", "note-title"}


class _RichSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, void=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, void=True)

    def _open(self, tag: str, attrs: list[tuple[str, str | None]], void: bool) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in {"h1", "h2"}:
            tag = "h3"
        if tag not in _RICH_TAGS:
            return
        classes = []
        for key, value in attrs:
            if key == "class" and value:
                classes = value.split()
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag == "div":
            tag = "p"
        size = "note-title" if "note-title" in classes else "note-lg" if "note-lg" in classes else ""
        if size and tag in {"p", "li", "h3"}:
            self.parts.append(f'<{tag} class="{size}">')
        else:
            self.parts.append(f"<{tag}>")
        if void:
            self.parts.append(f"</{tag}>")
        else:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        if tag in {"h1", "h2"}:
            tag = "h3"
        if tag == "div":
            tag = "p"
        if tag == "br" or tag not in _RICH_TAGS:
            return
        if tag in self.stack:
            while self.stack:
                opened = self.stack.pop()
                self.parts.append(f"</{opened}>")
                if opened == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        self.parts.append(html.escape(data))

    def result(self) -> str:
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")
        return "".join(self.parts)


class _RichText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def sanitize_rich_html(value: str) -> str:
    parser = _RichSanitizer()
    parser.feed(value)
    parser.close()
    return parser.result().strip()


def rich_plain_text(value: str) -> str:
    parser = _RichText()
    parser.feed(value)
    parser.close()
    return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def memo_content_from_payload(payload: dict, current: str | None = None) -> str:
    if current is not None and "content" not in payload and payload.get("content_format") != "rich":
        return current
    raw = str(payload.get("content", "") if current is None or "content" in payload else current).strip()
    if payload.get("content_format") == "rich":
        cleaned = sanitize_rich_html(raw)
        if len(rich_plain_text(cleaned)) > 4000 or len(cleaned) > 12000:
            raise AppError("单条感悟请控制在 4000 个字以内")
        return cleaned
    if len(raw) > 4000:
        raise AppError("单条感悟请控制在 4000 个字以内")
    return raw
