# IVN Swing – strategi og integrationsspecifikation

Status: forslag på feature-branch; ikke tilkoblet den aktive scanner eller UI endnu.

## Formål
Separat swingstrategi for Ivanhoe Mines (Yahoo Finance: `IVN.TO`, Toronto Stock Exchange). IVN er **ikke** medlem af Nasdaq-100 og må ikke inkluderes i Nasdaq-universets benchmark, screen eller eksisterende 1H-signaler.

## Horisont og data
- Primært 1D (afsluttede handelsdage), 1W som regimefilter, 4H kun til entry-finetuning.
- Hold typisk 2–12 uger; op til 3–6 måneder ved fortsat optrend.
- Daglig screening efter Toronto-børsens lukning; tidszoner/DST skal håndteres eksplicit.
- Verificér kurs, corporate actions, volumen og datatilgængelighed; `yfinance` er ikke et handelsfeed.

## Signallogik (foreslået, kræver backtest)
- WAIT: Ingen bekræftet vending, utilstrækkelige data eller ugunstigt risk/reward.
- BUY-kandidat: Efter en korrektion ses højere dagsbund / brud på seneste swing-high, RSI(14) stiger fra oversolgt område, og mindst én uafhængig bekræftelse (MACD-histogram forbedres eller kurs bryder MA20). Volumen vurderes mod 20D median. Kræv forventet reward/risk >= 2 før køb.
- HOLD: Aktiv position uden exittrigger; trailing stop beregnes med ATR(14) og seneste higher low.
- SELL: Luk ved brud på defineret stop, trendbrud eller bekræftet bearish reversal; delvis gevinst ved modstand og efterfølgende trailing stop er valgfrit.
- Undgå lookahead: indikatorer og beslutninger må kun bruge afsluttede bars; signal kan først handles efter dets tidsstempel.
- Undgå gentagne notifikationer for samme signal (ticker + strategi + signaldato + retning).

## Risikostyring
- Maks. 0,5–1,0 % af den *separat definerede swingkapital* i planlagt risiko pr. handel.
- Positionsstørrelse = min(risikobudget / entry-stop afstand, kapital-/positionsloft), med CAD/DKK-konvertering.
- ATR-baseret stop under teknisk støtte; kursgab kan give større tab end budgetteret.
- Handel kun ved dokumenteret likviditet; indregn spread, kurtage, valutakurs og slippage.
- Ingen automatisk averaging down eller ordreafgivelse.

## UI: fælles fane 'Other strategies'
Fanen skal kunne rumme flere selvstændige aktiestrategier, begyndende med IVN.TO. Hver aktie skal have sin egen konfiguration, signalhistorik, risikostyring og separat status; eksisterende Nasdaq-100-strategier må ikke påvirkes. Brug en aktievælger og vis pris og as-of dato, trend 1D/1W, RSI14, MACD, MA20/50, ATR14, støtte/modstand, entry/stop/targets, R/R, status BUY/HOLD/SELL/WAIT, begrundelse, signalhistorik og datakvalitet. Position/entry må kun vises som faktiske, når brugeren har registreret en position; ellers WATCHLIST/WAIT.

## Kvalitetsgate inden merge
1. Enhedstest af indikatorer, signalregler, stops, valutakonvertering og manglende data.
2. Backtest på tilstrækkeligt historisk 1D-data med walk-forward/out-of-sample, omkostninger og drawdown.
3. Verificér at eksisterende Nasdaq-strategier og CI fortsat er uændrede og grønne.
4. Paper-trade før live brug.
