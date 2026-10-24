#!/usr/bin/env bash
# Scan everything git would publish (tracked + untracked, minus .gitignore) for private or unsuitable content.
#   scripts/prepush_scan.sh            exit 0 only when every category has 0 hits
# Categories: secrets, home paths, e-mail addresses, account names (@handle), video files, Polish text in
# code and English docs, references to the author's own folders and names.
# Polish is a supported source language, so files that carry the marker "polish-lexicon" or "polish-fixtures"
# (language patterns and Polish test sentences), README.pl.md and prompts/knowledge.txt (it names the Polish step
# labels the model must use for Polish sources) are not scanned for Polish; they are listed.
# Exception, log and CLI messages (raise, print, logging, warnings, echo, exit) must be English everywhere,
# including in those marked files: Polish stays only in the language lexicon and in test fixtures.
set -u
cd "$(dirname "$0")/.."

FILES=()
while IFS= read -r -d '' f; do [ -f "$f" ] && FILES+=("$f"); done < <(git ls-files -z --cached --others --exclude-standard)
SELF="scripts/prepush_scan.sh"

TOTAL=0
report() { # category, hits (multi-line text)
  local n=0
  [ -n "$2" ] && n=$(printf '%s\n' "$2" | grep -c .)
  printf '%-34s %s\n' "$1" "$n"
  if [ "$n" -gt 0 ]; then printf '%s\n' "$2" | head -20 | sed 's/^/    /'; fi
  TOTAL=$((TOTAL + n))
}
scan() { # extended regex, optional perl-style exclude regex for lines; searches text files except this script
  local out=""
  for f in "${FILES[@]}"; do
    [ "$f" = "$SELF" ] && continue
    case "$f" in *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.skill|*.zip|*.ico|*.lock) continue ;; esac
    out+="$(grep -nIE -- "$1" "$f" 2>/dev/null | { if [ -n "${2:-}" ]; then grep -vE -- "$2"; else cat; fi; } | sed "s|^|$f:|")"$'\n'
  done
  printf '%s' "$out" | grep . || true
}

echo "Files in scope: ${#FILES[@]}"

report "secrets (keys, tokens)" "$(scan '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY|(api[_-]?key|secret|password|token)[A-Za-z_]*[ ]*[:=][ ]*["'"'"'][^"'"'"' ]{12,}|Bearer [A-Za-z0-9._-]{20,}|ANTHROPIC_API_KEY=[^ ]+)')"
report "home paths (/Users, /home)" "$(scan '(/Users/[A-Za-z0-9_.-]+|/home/[A-Za-z0-9_.-]+|C:\\Users\\)' '/home/runner')"
report "e-mail addresses" "$(scan '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}')"

# @handle that is not a decorator, a locator (@12, @s) or a known fictional name used in tests
report "account names (@handle)" "$(scan '(^|[^A-Za-z0-9_@/.-])@[A-Za-z][A-Za-z0-9_.]{2,}' '@(pytest|dataclass|classmethod|staticmethod|property|contextlib|functools|acme|someone|exact|example\.handle|types|v[0-9]|main|latest)\b')"

VIDEOS=""
for f in "${FILES[@]}"; do case "$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')" in *.mp4|*.mov|*.m4v|*.webm|*.mkv|*.avi|*.wmv|*.flv) VIDEOS+="$f"$'\n' ;; esac; done
report "video files" "$VIDEOS"

PL_FILES=(); PL_SKIPPED=()
for f in "${FILES[@]}"; do
  [ "$f" = "$SELF" ] && continue
  case "$f" in *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.skill|*.lock|*/OUTPUT/*|*.mp4|*.wav) continue ;; esac
  if [ "$f" = "README.pl.md" ] || [ "$f" = "prompts/knowledge.txt" ] || grep -qE 'polish-(lexicon|fixtures)' "$f" 2>/dev/null; then PL_SKIPPED+=("$f"); else PL_FILES+=("$f"); fi
done
PL_OUT=""
PL_RE='[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]|\b(jest|oraz|się|który|która|które|przez|jako|jeśli|więc|także|jednak|plik|pliki|uruchom|wyniki|karta|karty)\b'
for f in "${PL_FILES[@]}"; do PL_OUT+="$(grep -nIE -- "$PL_RE" "$f" 2>/dev/null | sed "s|^|$f:|")"$'\n'; done
report "Polish text in code / EN docs" "$(printf '%s' "$PL_OUT" | grep . || true)"
echo "    (skipped on purpose, Polish is a supported source language: ${PL_SKIPPED[*]:-none})"

# Messages are checked in every .py/.sh file (marked ones too). Polish words without diacritics count, so
# "Brak klatki ..." is caught. Lexicon dictionaries and test sentences are not on raise/print/log lines.
MSG_LINE='(raise |Error\(|Exception\(|print\(|logger?\.|logging\.|warnings\.warn|warn\(|echo |sys\.exit|SystemExit|typer\.|click\.)'
MSG_PL='[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]|\b(brak|nie|nieznany|nieprawidłowy|błąd|plik|pliku|klatki|klatka|podczas|lokalnego|skanowania|zbyt|wymaga|uruchom|spróbuj|sprobuj|podaj|użyj|uzyj|lub|dla|tylko|musi|należy|nalezy|katalog|wideo|film|zapis|odczyt|przetwarzani[ea]|zakończono|zakonczono|wynik|jest|oraz|się|który)\b'
MSG_OUT=""
for f in "${FILES[@]}"; do
  [ "$f" = "$SELF" ] && continue
  case "$f" in *.py|*.sh) ;; *) continue ;; esac
  MSG_OUT+="$(grep -nIE -- "$MSG_LINE" "$f" 2>/dev/null | grep -iE -- "$MSG_PL" | sed "s|^|$f:|")"$'\n'
done
report "Polish in error / log messages" "$(printf '%s' "$MSG_OUT" | grep . || true)"

report "own folders, names, projects" "$(scan '(IQ Mind Reader|Reel-?Lab|Claude-Detector|~/Desktop|/Desktop/|_ARCHIWUM|Piotr|Dominik|iCloud|Hetzner|\.ssh|Superbet|Sport Betting|Stock Betz|tiktok\.com/@|instagram\.com/[A-Za-z0-9_.]+/?$)')"

echo "----"
echo "TOTAL HITS: $TOTAL"
[ "$TOTAL" -eq 0 ]
