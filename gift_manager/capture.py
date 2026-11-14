"""Quick capture of a product page: the browser bookmarklet and the values it sends.

The bookmarklet runs in the user's browser on a shop page, reads the product metadata already
in the page and opens the capture page with it in the query string. Nothing is fetched by the
server. The captured values are untrusted: each one is cleaned on its own and dropped when it is
not usable, so a bad value never blocks the others.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from decimal import InvalidOperation
from urllib.parse import quote
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.urls import reverse

from gift_manager.validators import ALLOWED_URL_SCHEMES
from gift_manager.validators import validate_http_url

TITLE_MAX_LENGTH = 255
URL_MAX_LENGTH = 2000
NOTES_MAX_LENGTH = 150
# Prices are stored with 10 digits, 2 of them decimals
PRICE_LIMIT = Decimal(100000000)

_validate_url_syntax = URLValidator(schemes=sorted(ALLOWED_URL_SCHEMES))


@dataclass(frozen=True)
class Capture:
    """The usable values of a captured product page."""

    title: str = ""
    url: str = ""
    price: Decimal | None = None
    notes: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.title or self.url)

    @property
    def price_text(self) -> str:
        """The price with a dot as decimal separator, as number inputs expect it."""
        return "" if self.price is None else f"{self.price:.2f}"


def _clean_text(value: str, max_length: int) -> str:
    return " ".join((value or "").split())[:max_length].strip()


def _clean_url(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > URL_MAX_LENGTH:
        return ""
    try:
        # The raw value must already be an http(s) URL: no scheme is ever guessed
        validate_http_url(value)
        _validate_url_syntax(value)
    except ValidationError:
        return ""
    return value


def _normalize_decimal(text: str) -> str | None:
    """Return ``text`` with a dot as its only separator, or None when it cannot be told.

    Shops write "1,299.00", "1.299,00" or "24,99". With both separators the last one is the
    decimal mark. A lone dot is the decimal mark (the metadata standards ask for it). A lone
    comma is one too, except before exactly three digits ("1,299"), which may be thousands.
    """
    last_comma, last_dot = text.rfind(","), text.rfind(".")
    if last_comma == -1:
        return text
    if last_dot != -1:
        thousands, decimal = (",", ".") if last_dot > last_comma else (".", ",")
        return text.replace(thousands, "").replace(decimal, ".")
    if text.count(",") > 1:
        return text.replace(",", "")
    if len(text) - last_comma - 1 == 3:
        return None
    return text.replace(",", ".")


def _clean_price(value: str) -> Decimal | None:
    text = _normalize_decimal("".join((value or "").split()))
    if text is None:
        return None
    try:
        price = Decimal(text)
        if not price.is_finite() or price < 0:
            return None
        price = price.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return price if price < PRICE_LIMIT else None


def clean_capture(params, user_currency: str) -> Capture:
    """Return the usable values of the query-string ``params`` sent by the bookmarklet.

    The price is kept only when the page states a currency and it is the user's own: a price in
    another or an unknown currency would be read as an amount in the user's currency.
    """
    currency = (params.get("currency") or "").strip().upper()
    same_currency = bool(currency) and currency == (user_currency or "").upper()
    return Capture(
        title=_clean_text(params.get("title"), TITLE_MAX_LENGTH),
        url=_clean_url(params.get("url")),
        price=_clean_price(params.get("price")) if same_currency else None,
        notes=_clean_text(params.get("notes"), NOTES_MAX_LENGTH),
    )


def _with_query(url: str, values: dict[str, str]) -> str:
    query = urlencode({name: value for name, value in values.items() if value})
    return f"{url}?{query}" if query else url


def target_urls(capture: Capture) -> dict[str, str]:
    """Return the creation pages of a wish, a gift plan and a gift, prefilled with ``capture``."""
    return {
        "wish": _with_query(
            reverse("gift_manager:wish_create"),
            {
                "title": capture.title,
                "url": capture.url,
                "price_hint": capture.price_text,
                "notes": capture.notes,
            },
        ),
        "plan": _with_query(
            reverse("gift_manager:relation_guided_create"),
            {
                "new_gift-name": capture.title,
                "new_gift-url": capture.url,
                "new_gift-price": capture.price_text,
            },
        ),
        "gift": _with_query(
            reverse("gift_manager:gift_create"),
            {"name": capture.title, "url": capture.url, "price": capture.price_text},
        ),
    }


# Kept small: it is stored whole in the bookmark. It only reads the page and opens the capture
# page; ``void`` keeps the browser from replacing the shop page with the script's result.
_BOOKMARKLET_SOURCE = """
void(function(){
var d=document,C=__CAPTURE_URL__,E=encodeURIComponent;
function m(s){var e=d.querySelector(s);return(e&&e.getAttribute('content'))||''}
function o(n){return m('meta[property="og:'+n+'"]')||m('meta[property="product:'+n+'"]')}
var l=d.querySelector('link[rel="canonical"]'),u=(l&&l.href)||location.href,
t=m('meta[property="og:title"]')||m('meta[name="twitter:title"]')||d.title||'',
p=o('price:amount'),c=o('price:currency'),n=m('meta[property="og:description"]');
function w(j){
if(!j||typeof j!='object')return;
if(Array.isArray(j)){j.forEach(w);return}
if(j['@graph'])w(j['@graph']);
var f=j.offers;if(Array.isArray(f))f=f[0];
if(f&&!p&&(f.price||f.lowPrice)){p=f.price||f.lowPrice;c=f.priceCurrency||''}
}
if(!p)d.querySelectorAll('script[type="application/ld+json"]').forEach(function(s){
try{w(JSON.parse(s.textContent))}catch(e){}});
function q(a,b){return C+'?url='+E(u)+'&title='+E(a)+'&price='+E(p)
+'&currency='+E(c)+'&notes='+E(b)}
t=String(t).trim().slice(0,255);n=String(n).trim().slice(0,150);
var x=q(t,n);if(x.length>2000)x=q(t,'');if(x.length>2000)x=q(t.slice(0,80),'');
var W=window.open(x,'_blank');if(W){try{W.opener=null}catch(e){}}else{location.href=x}
}())
"""


def build_bookmarklet(capture_url: str) -> str:
    """Return the ``javascript:`` URL of the bookmarklet opening ``capture_url``."""
    source = "".join(line.strip() for line in _BOOKMARKLET_SOURCE.splitlines())
    # json.dumps makes the URL a safe JavaScript string literal whatever it contains
    return "javascript:" + quote(source.replace("__CAPTURE_URL__", json.dumps(capture_url)))
