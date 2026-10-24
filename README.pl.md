# Claude-Video-Journalist

**Zamienia krótkie filmy w wiedzę z dowodami dla agentów Claude.**

Wchodzi film (plik, folder albo URL). Wychodzą zwykłe pliki Markdown, które agent może tanio wczytać i sprawdzić: indeks, karta twierdzeń dla każdego filmu, wierny artykuł oraz transkrypt i tekst z ekranu jako dowód. Każda liczba w karcie ma sekundę w filmie i jest sprawdzona zarówno z mową, jak i z ekranem.

Działa na Twoim komputerze: ffmpeg, faster-whisper i OCR robią część mechaniczną, a **jedno wywołanie Claude CLI na nowy film** pisze kartę. Bez serwera, bez klucza API w repozytorium. Wersja angielska: [README.md](README.md).

## Czym różni się od skryptów „film → transkrypt/streszczenie”

1. **Wyjście dla agenta, nie dla czytelnika.** Agent czyta `INDEX.md`, otwiera tylko potrzebne karty, a archiwum tylko po to, by sprawdzić liczbę. W 82 kartach z wcześniejszych przebiegów karta miała średnio ok. 630 tokenów (znaki / 4, szacunek), transkrypt ok. 370, OCR ok. 390. Przy filmach 1-2 minutowych karta **nie jest** mniejsza od surowego transkryptu; daje strukturę (teza, liczby, metoda, braki) i ładowanie na żądanie. Oszczędności dla długich filmów nie mierzyliśmy.
2. **Dowód przy każdej liczbie.** Liczba w karcie ma `@s` (sekunda). `number_check` mówi, czy liczba padła w mowie, jest na ekranie, czy w obu, i oznacza `conflict(OCR:x)` przy rozbieżności. Walidator w kodzie (nie model) odrzuca liczby spoza transkryptu i OCR, wycina cytaty „z ekranu”, których na ekranie nie ma, i sprawdza nazwy własne oraz etykiety tabel. Nic spoza materiału nie jest dodawane.
3. **Twierdzenia to hipotezy z cyklem życia.** Karta zaczyna jako `status: untested` i `unverified_claim` („według autora”). Agent przesuwa ją `untested -> in_test -> confirmed | rejected` i zapisuje wyniki w `agent_notes`; `rebuild` nie nadpisze karty, którą agent ruszył.
4. **Treść, nie styl.** Zapisuje, co film mówi i pokazuje. Bez montażu, muzyki i kamery.
5. **Język źródłowy zostaje.** Film angielski daje pliki angielskie, polski polskie. Bez tłumaczenia.
6. **Lokalnie, jedno płatne wywołanie na film, cache po SHA-256.** Ten sam plik nie jest analizowany dwa razy. Przebudowa kart po zmianie kodu czyta cache i nic nie kosztuje.

## Co zmierzono (przeczytaj, zanim zaufasz)

- Na wymyślonym przykładzie (`examples/sample`, 48 s): jedno wywołanie Claude, **0,0457 USD-ekwiwalentu**, `check` = 0 problemów z pokryciem. W tym samym przebiegu walidator zrobił 3 odrzucenia, z czego 2 usunęły poprawną treść (etykietę tabeli): `false_rejection_rate` 66,7% na 3 przypadkach. Próbka za mała na wnioski, ale to realna słabość.
- Wcześniejsze przebiegi na ok. 80 prawdziwych filmach (nie ma ich w repozytorium): 0 naruszeń pokrycia, `false_rejection_rate` 5,4% (cel 3%), `screen_attribution_ok` 100%, 30 z 30 liczb w ocenianych kartach pokryte w źródle, 0,10-0,14 USD-ekwiwalentu na film. Jakość oceniono w 8 niezależnych ocenach AI w czterech rundach (ostatnia: średnio 80 pkt na prawdziwej partii). To dane z notatek projektu; filmów nie publikujemy, więc nie da się ich odtworzyć z tego repozytorium.
- Narzędzie zapisuje, co film twierdzi. Nie sprawdza, czy to prawda, a ASR może się przesłyszeć (`verified_by_ear: false` w każdym archiwum).

## Instalacja i użycie

```bash
git clone <adres-repozytorium> Claude-Video-Journalist && cd Claude-Video-Journalist
./install.sh                                     # uv, ffmpeg, yt-dlp, pakiety Pythona (szczegóły: install.md)
uv run python -m vjournalist preflight
uv run python -m vjournalist read <plik | folder | URL>
```

Potrzebne zalogowane Claude Code CLI (`claude auth login`). Pierwszy przebieg pobiera model Whisper `small` (ok. 460 MB). `read --dry-run` pokazuje, co zostałoby przeanalizowane, zanim cokolwiek wydasz.

## Dwa skille

- [`video-read`](skills/video-read/SKILL.md): produkuje pliki z pliku, folderu lub URL (potrzebuje pakietu Pythona z tego repozytorium).
- [`claim-cards`](skills/claim-cards/SKILL.md): instrukcja dla agenta-konsumenta (indeks najpierw, plan testu z karty, weryfikacja liczby przez `tx`, zapis wyników). Czysty tekst, bez zależności.

Wgranie: `./install.sh --skills` linkuje je do `~/.claude/skills/`, albo skopiuj foldery, albo zbuduj paczkę `.skill`. Paczka `.skill` zawiera same instrukcje i cienkie skrypty, więc ustaw `VJOURNALIST_HOME` na sklonowane repozytorium.

## Testy i znane ograniczenia

`uv run pytest -q` i `uv run ruff check .` działają bez Whispera, sieci i logowania do Claude. `scripts/prepush_scan.sh` sprawdza repozytorium przed pushem. Ograniczenia i plany: [ROADMAP.md](ROADMAP.md).

## Licencja

MIT, zob. [LICENSE](LICENSE). Przetwarzaj tylko filmy, do których masz prawo; narzędzie pobiera lokalnie, a do Claude CLI wysyła tekst i kilka klatek, nigdy pliku wideo.
