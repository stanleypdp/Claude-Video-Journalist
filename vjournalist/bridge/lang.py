# polish-lexicon: this file holds Polish-language patterns/labels on purpose (Polish is a supported source language).
"""Read writes in the language of the transcript and never translates.

Field names (`## claim`) are fixed identifiers. Everything else the code writes (table headings, legends,
`local_rejections`, `not_stated` gaps, assumptions, derived labels) follows the transcript language: one label
map per `lang` (`MESSAGES`), Polish only for Polish sources.
"""

import re

POLISH_CHARS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
# Polish function words that are not English words; `to`, `a`, `w`, `na`, `film` are deliberately absent.
POLISH_STOP = re.compile(
    r"\b(?:jest|oraz|się|nie|który|która|które|którzy|jako|dla|przez|ale|tylko|również|czy|ponieważ|"
    r"według|autor\w*|twierdzi|pokazuje|mówi|przed|bez|nad|lub|albo|gdy|gdzie|kiedy|jeśli|więc|także|jednak|"
    r"wynik\w*|zysk\w*|koszt\w*|ekran\w*|dane|danych)\b",
    re.I,
)
QUOTED = re.compile(r"[„“\"][^„”“\"]*[”\"]")

MESSAGES = {
    "pl": {
        "unknown": "unknown — twierdzenie wymaga weryfikacji źródła",
        "gap": "{label}: brak w dostarczonym tekście źródłowym",
        "assumption": "założenie: {text}",
        "assumption_result": "założenie: wynik {value} jest {label}; autor nie łączy tego z tą liczbą",
        "gap_note": "{hi}{unit} i {lo}{unit}: różnica {gap} = {share} większej liczby (wyliczone, pole derived).",
        "author_said": " Autor: „{text}”",
        "label_gap": "różnica",
        "label_share": "udział w większej liczbie",
        "data_table": "tabeli danych",
        "action": "[akcja]",
        "effect": "[efekt]",
        "screen_legend": "Pierwsze i ostatnie pojawienie; ≈ = niepewny OCR.",
        "screen_filtered": "Odfiltrowano: uszkodzone tokeny {damaged}, etykiety osi {axis}, szum {noise}; scalone warianty {merged}.",
        "number_check_legend": "ok=mowa i ekran; speech_only=tylko mowa; screen_only=tylko ekran (OCR po filtrze)",
        "table_heading": "Dane z wykresów i plansz",
        "table_header": "| Czas | Dane | Wartość | Źródło | Pewność |",
        "src_screen": "ekran",
        "src_screen_speech": "ekran+mowa",
        "src_speech": "mowa",
        "src_computed": "wyliczone",
        "conf_exact": "dokładna",
        "conf_approx": "przybliżona",
        "conf_speech": "mowa",
        "conf_computed": "wyliczona",
        "unlabeled": "bez etykiety",
        "method_none": "nie podano",
        "key_article": "artykuł",
        "none_given": "brak w źródle",
        "version_conflict": "Na ekranie: {name} {shown}; w mowie: {name} {spoken} (rozbieżność wersji).",
        "rej_number": "liczba bez pokrycia w transkrypcie i OCR ({numbers})",
        "rej_number_source": "liczba bez pokrycia w źródle ({numbers})",
        "rej_number_field": "{key}: {text} — liczba {numbers} zastąpiona [n/a] (brak w transkrypcie i OCR)",
        "rej_cut": "{key}: usunięto fragment {cuts} z: {text}… — brak w OCR i mowie",
        "rej_sentence": "{key}: {text} — {reason}",
        "rej_derived": "derived: {value} = {formula} — formuła niepoprawna lub z liczbą bez pokrycia",
        "rej_table_label_number": "tabela: z etykiety „{label}” usunięto liczbę bez pokrycia ({numbers})",
        "rej_table_number": "tabela: {label} = {value} — liczba bez pokrycia",
        "rej_table_value": "tabela: {label} = {value} — wartość nie występuje w OCR",
        "rej_table_unlabeled": "tabela: etykieta „{label}” nie występuje w OCR przy liczbie {value}; wiersz zapisano bez etykiety",
        "rej_quote": "{key}: cytat „{quote}” podany jako z ekranu nie występuje w OCR — oznaczono [not in OCR]",
        "rej_stub": "{key}: {text} — zdanie bez treści po usunięciu niepotwierdzonego cytatu",
        "rej_general": "{key}: {text} — wiedza spoza materiału (uogólnienie bez oparcia w źródle)",
        "rej_moved": "{text} — przeniesione z karty (profil bez agent_notes)",
        "rej_conflict_version": "ekran pokazuje {screen}, mowa podaje {speech}",
        "reason_no_ocr": "brak w OCR: {tokens}",
        "reason_no_source": "brak w mowie i OCR: {tokens}",
        "reason_screen_visual": "opis wyglądu bez odpowiednika w OCR ({english})",
        "reason_screen_token": "twierdzenie o ekranie bez tokenu do sprawdzenia w OCR",
        "reason_stub": "kikut zdania po usunięciu fragmentu ({why})",
        "rej_table_trimmed": "tabela: z etykiety „{label}” usunięto niepotwierdzone słowa „{removed}” przy liczbie {value}",
        "rej_reattributed": "{key}: cytat „{quote}” podany jako z ekranu nie występuje w OCR, ale pada w mowie — atrybucję zmieniono na mowę",
        "rej_name": "{key}: nazwa własna „{name}” nie występuje w transkrypcie ani OCR — {action}",
        "name_generic": "zastąpiona opisem rodzajowym",
        "name_marked": "oznaczona [name not in source]",
        "rejections_note": "Diagnostyka: treści usunięte lub poprawione przez kontrolę źródła. To nie jest źródło faktów; nie odtwarzaj stąd danych.",
        "spoken_tag": "[w mowie]",
        "spoken_line": "wypowiedź autora",
        "brief_rej_number_field": "{key}: liczba bez pokrycia zastąpiona [n/a]",
        "brief_rej_cut": "{key}: usunięto fragment, którego nie ma w OCR ani w mowie",
        "brief_rej_sentence": "{key}: zdanie usunięte — {reason}",
        "brief_rej_derived": "derived: pozycja usunięta — formuła niepoprawna lub liczba bez pokrycia",
        "brief_rej_table_label_number": "tabela: z etykiety usunięto liczbę bez pokrycia",
        "brief_rej_table_number": "tabela: wiersz usunięty — liczba bez pokrycia",
        "brief_rej_table_value": "tabela: wiersz usunięty — wartości nie ma w OCR",
        "brief_rej_table_unlabeled": "tabela: etykieta niepotwierdzona przy liczbie; wiersz bez etykiety",
        "brief_rej_table_trimmed": "tabela: z etykiety usunięto niepotwierdzone słowa",
        "brief_rej_quote": "{key}: cytat podany jako z ekranu nie występuje w OCR — oznaczono [not in OCR]",
        "brief_rej_reattributed": "{key}: cytat podany jako z ekranu pada w mowie — atrybucję zmieniono na mowę",
        "brief_rej_stub": "{key}: zdanie usunięte — brak treści po usunięciu niepotwierdzonego cytatu",
        "brief_rej_general": "{key}: zdanie usunięte — wiedza spoza materiału",
        "brief_rej_moved": "założenie przeniesione z karty (profil bez agent_notes)",
        "brief_rej_name": "{key}: nazwa własna spoza transkryptu i OCR — {action}",
    },
    "en": {
        "unknown": "unknown — claim requires source verification",
        "gap": "{label}: not stated in the provided source text",
        "assumption": "assumption: {text}",
        "assumption_result": "assumption: result {value} is {label}; the author does not tie this to this number",
        "gap_note": "{hi}{unit} and {lo}{unit}: difference {gap} = {share} of the larger figure (computed, field derived).",
        "author_said": " Author: “{text}”",
        "label_gap": "difference",
        "label_share": "share of the larger figure",
        "data_table": "the data table",
        "action": "[action]",
        "effect": "[effect]",
        "screen_legend": "First and last appearance; ≈ = uncertain OCR.",
        "screen_filtered": "Filtered: damaged tokens {damaged}, axis labels {axis}, noise {noise}; merged variants {merged}.",
        "number_check_legend": "ok=speech and screen; speech_only=speech only; screen_only=screen only (OCR after filter)",
        "table_heading": "Data from charts and slides",
        "table_header": "| Time | Data | Value | Source | Confidence |",
        "src_screen": "screen",
        "src_screen_speech": "screen+speech",
        "src_speech": "speech",
        "src_computed": "computed",
        "conf_exact": "exact",
        "conf_approx": "approximate",
        "conf_speech": "speech",
        "conf_computed": "computed",
        "unlabeled": "unlabeled",
        "method_none": "not stated",
        "key_article": "article",
        "none_given": "none given in the source",
        "version_conflict": "On screen: {name} {shown}; in speech: {name} {spoken} (version mismatch).",
        "rej_number": "number without coverage in transcript and OCR ({numbers})",
        "rej_number_source": "number without coverage in the source ({numbers})",
        "rej_number_field": "{key}: {text} — number {numbers} replaced by [n/a] (not in transcript or OCR)",
        "rej_cut": "{key}: removed fragment {cuts} from: {text}… — not in OCR or speech",
        "rej_sentence": "{key}: {text} — {reason}",
        "rej_derived": "derived: {value} = {formula} — invalid formula or a number without coverage",
        "rej_table_label_number": "table: removed a number without coverage ({numbers}) from label “{label}”",
        "rej_table_number": "table: {label} = {value} — number without coverage",
        "rej_table_value": "table: {label} = {value} — value is not in the OCR",
        "rej_table_unlabeled": "table: label “{label}” is not in the OCR next to {value}; row kept without a label",
        "rej_quote": "{key}: quote “{quote}” given as on-screen text is not in the OCR — marked [not in OCR]",
        "rej_stub": "{key}: {text} — sentence has no content left after removing an unverified quote",
        "rej_general": "{key}: {text} — knowledge from outside the material (generalization without source)",
        "rej_moved": "{text} — moved from the card (profile without agent_notes)",
        "rej_conflict_version": "the screen shows {screen}, the speech says {speech}",
        "reason_no_ocr": "not in OCR: {tokens}",
        "reason_no_source": "not in speech or OCR: {tokens}",
        "reason_screen_visual": "appearance description without a counterpart in the OCR ({english})",
        "reason_screen_token": "claim about the screen without a token to check in the OCR",
        "reason_stub": "sentence stub after removing a fragment ({why})",
        "rej_table_trimmed": "table: removed words not confirmed next to {value} (“{removed}”) from label “{label}”",
        "rej_reattributed": "{key}: quote “{quote}” given as on-screen text is not in the OCR but is spoken — attribution changed to the speech",
        "rej_name": "{key}: proper name “{name}” is not in the transcript or OCR — {action}",
        "name_generic": "replaced by a generic description",
        "name_marked": "marked [name not in source]",
        "rejections_note": "Diagnostics: content removed or corrected by the source check. Not a source of facts; do not rebuild data from it.",
        "spoken_tag": "[spoken]",
        "spoken_line": "spoken line",
        "brief_rej_number_field": "{key}: number without coverage replaced by [n/a]",
        "brief_rej_cut": "{key}: fragment that is not in the OCR or speech removed",
        "brief_rej_sentence": "{key}: sentence removed — {reason}",
        "brief_rej_derived": "derived: item removed — invalid formula or a number without coverage",
        "brief_rej_table_label_number": "table: number without coverage removed from a label",
        "brief_rej_table_number": "table: row removed — number without coverage",
        "brief_rej_table_value": "table: row removed — value is not in the OCR",
        "brief_rej_table_unlabeled": "table: label not confirmed next to the number; row kept without a label",
        "brief_rej_table_trimmed": "table: unconfirmed words removed from a label",
        "brief_rej_quote": "{key}: quote given as on-screen text is not in the OCR — marked [not in OCR]",
        "brief_rej_reattributed": "{key}: quote given as on-screen text is spoken — attribution changed to the speech",
        "brief_rej_stub": "{key}: sentence removed — no content left after removing an unverified quote",
        "brief_rej_general": "{key}: sentence removed — knowledge from outside the material",
        "brief_rej_moved": "assumption moved from the card (profile without agent_notes)",
        "brief_rej_name": "{key}: proper name not in the transcript or OCR — {action}",
    },
}
GAP_LABELS_EN = {
    "instrument/obiekt": "instrument/asset",
    "źródło danych": "data source",
    "okres badania": "study period",
    "liczebność próby": "sample size",
    "metoda": "method",
    "koszty": "costs",
    "istotność statystyczna": "statistical significance",
    "wersje": "versions",
    "warunki": "requirements",
    "dowody": "evidence",
    "ograniczenia": "limitations",
    "cena/koszt": "price/cost",
    "dostępność/wersja": "availability/version",
    "dowody/wyniki": "evidence/results",
}
STEP_TAGS = ("[akcja]", "[efekt]", "[action]", "[effect]")


def language(transcript):
    """Language code of the transcript (`en`, `pl`, ... or `unknown`)."""
    return str((transcript or {}).get("language") or "unknown").lower()


def say(lang, message, **fields):
    """Code-generated sentence in the transcript language (Polish only for Polish sources)."""
    return MESSAGES["pl" if lang == "pl" else "en"][message].format(**fields)


def table_headings():
    """Every table heading code has ever written: readers accept the Polish and the English one."""
    return tuple(m["table_heading"] for m in MESSAGES.values())


def split_article(article):
    """(prose, table text) at whichever table heading the article uses."""
    for heading in table_headings():
        if f"## {heading}" in article:
            prose, _, table = article.partition(f"## {heading}")
            return prose, table
    return article, ""


def source_kind(cell):
    """Canonical source of a table cell in any language: screen | screen+speech | speech | computed | None."""
    for m in MESSAGES.values():
        for kind, key in (("screen", "src_screen"), ("screen+speech", "src_screen_speech"), ("speech", "src_speech"), ("computed", "src_computed")):
            if cell == m[key]:
                return kind
    return None


def confidence_kind(cell):
    """Canonical confidence in any language: exact | approximate | speech | computed | None."""
    for m in MESSAGES.values():
        for kind, key in (("exact", "conf_exact"), ("approximate", "conf_approx"), ("speech", "conf_speech"), ("computed", "conf_computed")):
            if cell == m[key]:
                return kind
    return None


def is_table_header(line):
    return line.strip() in {m["table_header"] for m in MESSAGES.values()}


def gap_label(lang, label):
    return label if lang == "pl" else GAP_LABELS_EN[label]


def polish_in(text):
    """The first sign that `text` is Polish (diacritic or function word) outside verbatim quotes, else None."""
    plain = QUOTED.sub(" ", str(text))
    found = POLISH_CHARS.search(plain) or POLISH_STOP.search(plain)
    return found[0] if found else None


def content_texts(value):
    """(field, text) over the model-written content of a Read answer: title, tags, article, card, table."""
    card = value.get("card", {})
    skip = {"profile", "number_check", "local_rejections", "derived"}
    yield "title", value.get("title", "")
    for tag in value.get("tags", []):
        yield "tags", tag
    for paragraph in value.get("article", []):
        yield "article", paragraph.get("text", "")
    for row in value.get("screen_data", []):
        yield "screen_data", f"{row.get('label', '')} {row.get('value', '')}"
    for key, field in card.items():
        if key in skip:
            continue
        for text in field if isinstance(field, list) else [field]:
            if isinstance(text, str):
                yield key, text


def check_language(value, lang):
    """Raise when a `lang=en` answer contains Polish content (the model translated instead of quoting)."""
    if lang != "en":
        return
    for field, text in content_texts(value):
        if hit := polish_in(text):
            raise ValueError(
                f"Read field {field} is Polish (“{hit}”) but the transcript is English: "
                "write in the language of the transcript, never translate."
            )


_REASONS = (
    ("not in speech or OCR: ", "reason_no_source", "tokens"),
    ("brak w mowie i OCR: ", "reason_no_source", "tokens"),
    ("not in OCR: ", "reason_no_ocr", "tokens"),
    ("brak w OCR: ", "reason_no_ocr", "tokens"),
)
_VISUAL = re.compile(r"(?:appearance description without a counterpart in the OCR|opis wyglądu bez odpowiednika w OCR) \((.*)\)$")
_TOKENLESS = {
    MESSAGES["en"]["reason_screen_token"],
    MESSAGES["pl"]["reason_screen_token"],
}


def localize_reason(lang, reason):
    """Reasons produced by vjournalist.bridge.coverage are English identifiers; render them in the source language."""
    if not reason:
        return reason
    messages = MESSAGES["pl" if lang == "pl" else "en"]
    for prefix, key, field in _REASONS:
        if reason.startswith(prefix):
            return messages[key].format(**{field: reason[len(prefix) :]})
    if m := _VISUAL.match(reason):
        return messages["reason_screen_visual"].format(english=m[1])
    if reason in _TOKENLESS:
        return messages["reason_screen_token"]
    return reason
    for prefix, key, field in _REASONS:
        if reason.startswith(prefix):
            return MESSAGES["en"][key].format(**{field: reason[len(prefix) :]})
    if m := re.match(r"opis wyglądu bez odpowiednika w OCR \((.*)\)$", reason):
        return MESSAGES["en"]["reason_screen_visual"].format(english=m[1])
    if reason == "twierdzenie o ekranie bez tokenu do sprawdzenia w OCR":
        return MESSAGES["en"]["reason_screen_token"]
    return reason
