# Nasdaq-100 1H Swing Agent

En deterministisk long-only scanner baseret på 1H-trend/candlesticks og dagligt momentum, relativ styrke, beta og volumen.

## Regler

- Seneste afsluttede 1H-kurs > EMA50 > EMA200.
- Positive 5-, 21- og 63-handelsdages afkast.
- 63-dages afkast over Nasdaq-100 (`^NDX`).
- Seneste afsluttede dags volumen > gennemsnittet for de 20 foregående dage.
- 252-dages beta mod `^NDX` > 1,20, med mindst 126 observationer.
- Bekræftet bullish hammer, bullish engulfing, morning star, inside-bar breakout eller regelbaseret bull-flag breakout.
- Entry over signalbarens high plus 0,05 ATR.
- Stop under laveste low i de seneste 10 1H-bars minus 0,10 ATR.
- Target mindst 2,5 ATR og altid mindst R/R 2,0.
- Near-miss har præcis ét fejlet filter.
- Positionsstørrelse begrænses af både 300 kr. tabsrisiko og 4.000 kr. maksimal positionsværdi.
- Højst fem samtidige positioner; agenten åbner ikke handler og kan derfor ikke selv tælle eksisterende positioner.

## Installation og kørsel

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python swing_agent.py
```

Opdatér medlemslisten efter indeksændringer med `--refresh-universe`. Den medfølgende liste er dateret 1. august 2026.

Rapporter gemmes som Markdown og JSON i `reports/`. `state/previous_screen.json` bruges til ændringer siden seneste kørsel.

Kan Python ikke installeres lokalt, kan projektet køre direkte i GitHub Actions. Følg `GITHUB_SETUP.md`; den medfølgende workflowfil kan både startes manuelt og kører automatisk på hverdage kl. 22.30 dansk tid.

## Konfiguration

Standardopsætningen bruger 20.000 kr. kapital, 1,5 % maksimal tabsrisiko pr. handel, 20 % maksimal kapitalallokering pr. position og fem samtidige positioner. Seneste USD/DKK-kurs hentes via `DKK=X`. Positionsstørrelsen er det laveste heltalsresultat af risikoloftet og kapitalallokeringsloftet.

## Vigtige begrænsninger

- `yfinance` er egnet til prototype og paper trading, ikke som garanteret handelsfeed.
- 1H-data er begrænset til cirka 60 dage.
- En lokalt valideret Nasdaq-100-liste medfølger. Valgfri opdatering hentes fra den offentlige komponenttabel og accepteres kun med mindst 90 unikke symboler.
- Signalet bruger kun afsluttede ordinære market-hours bars.
- Et månedligt resultatmål indgår ikke i signalreglerne. Evaluer strategien på forventningsværdi, drawdown og out-of-sample-resultater før rigtig handel.
- Output er screening, ikke finansiel rådgivning eller en ordre om køb/salg.
