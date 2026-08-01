# GitHub-opsætning uden lokal Python

## Første opsætning

1. Opret et nyt **privat** repository på GitHub, fx `nasdaq100-swing-agent`.
2. Pak ZIP-filen ud, åbn mappen `nasdaq100_swing_agent`, og upload **indholdet i mappen** til repositoryets rod. `.github` skal ligge direkte i repositoryets rod.
3. Kontrollér under fanen **Actions**, at workflowet `Daily Nasdaq-100 swing screen` vises.
4. Åbn workflowet og vælg **Run workflow** for den første manuelle test.
5. Åbn den færdige kørsel. Rapporten kan hentes under **Artifacts**, og Markdown/JSON-filerne gemmes også i mappen `reports` i repositoryet.

## Automatisk kørsel

Workflowet kører mandag–fredag kl. 22.30 i tidszonen `Europe/Copenhagen`. GitHub kan starte en planlagt kørsel lidt senere under høj belastning.

## Hvis rapporten ikke kan gemmes

Kontrollér repositoryets **Settings → Actions → General → Workflow permissions**. Workflowet skal have tilladelse til at skrive indhold, ellers kan rapportfilen stadig hentes som artifact, men den kan ikke gemmes permanent i repositoryet.

## Hvis Yahoo begrænser data

Åbn workflowkørslen og se loggen under `Run screening`. En fejl eller tom dataleverance må ikke fortolkes som, at der ingen setups er. Vent og kør workflowet manuelt igen senere. `yfinance` er prototypedata, ikke et garanteret markedsfeed.
