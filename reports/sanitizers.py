"""Saneamiento de HTML enviado por usuarios.

El editor de respuestas de tareas es un `contenteditable`, asi que envia HTML.
En vez de intentar borrar lo peligroso (lista negra, siempre evadible) este
modulo reconstruye el HTML desde cero y solo emite lo que esta explicitamente
permitido: cualquier etiqueta, atributo o esquema de URL desconocido se
descarta en silencio.
"""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = {
    "a": {"href", "title"},
    "b": set(),
    "br": set(),
    "code": set(),
    "em": set(),
    "i": set(),
    "li": set(),
    "ol": set(),
    "p": set(),
    "s": set(),
    "span": set(),
    "strong": set(),
    "u": set(),
    "ul": set(),
}

VOID_TAGS = {"br"}

# Etiquetas cuyo contenido de texto tampoco debe conservarse.
DROP_CONTENT_TAGS = {"script", "style", "template", "iframe", "object", "embed"}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def _safe_url(value):
    """Devuelve la URL si su esquema es seguro, o None."""
    candidate = (value or "").strip()
    if not candidate:
        return None
    # Un esquema con espacios o saltos de linea intercalados ("java\nscript:")
    # se normaliza antes de evaluarlo para que no pase disfrazado.
    normalized = "".join(candidate.split()).lower()
    if normalized.startswith("//"):
        return None
    parsed = urlparse(normalized)
    if not parsed.scheme:
        # Enlaces relativos: se aceptan solo si no parecen un esquema raro.
        return candidate if ":" not in normalized.split("/")[0] else None
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        return None
    return candidate


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            if tag in DROP_CONTENT_TAGS:
                self.skip_depth += 1
            return
        if tag in DROP_CONTENT_TAGS:
            self.skip_depth = 1
            return
        allowed_attrs = ALLOWED_TAGS.get(tag)
        if allowed_attrs is None:
            return

        rendered = []
        for name, value in attrs:
            name = (name or "").lower()
            if name not in allowed_attrs:
                continue
            if name == "href":
                value = _safe_url(value)
                if value is None:
                    continue
            rendered.append(f' {name}="{escape(value or "", quote=True)}"')

        if tag in VOID_TAGS:
            self.parts.append(f"<{tag}{''.join(rendered)}>")
            return
        self.parts.append(f"<{tag}{''.join(rendered)}>")
        self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag in DROP_CONTENT_TAGS:
                self.skip_depth -= 1
            return
        if tag in VOID_TAGS or tag not in ALLOWED_TAGS:
            return
        if tag not in self.open_tags:
            return
        # Cierra tambien lo que quedo abierto por dentro, para no emitir
        # marcado desbalanceado.
        while self.open_tags:
            current = self.open_tags.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.parts.append(escape(data, quote=False))

    def result(self):
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def sanitize_rich_text(value):
    """Sanea HTML de usuario dejando solo formato basico y enlaces seguros."""
    if not value:
        return ""
    parser = _Sanitizer()
    parser.feed(str(value))
    parser.close()
    return parser.result().strip()
