# Fil Phillies

Agrégateur de presse sur les Phillies de Philadelphie : toutes les news des meilleures
sources dans un seul fil, avec le lien vers chaque article original.

**Aucune traduction, aucune API payante, aucune clé, aucun compte.**

## Site en ligne

Publié automatiquement par GitHub Pages à chaque mise à jour du fil.

## Comment ça marche

```
GitHub Actions (cron 30 min)
   └─ collect.py   ── 12 sources : flux RSS, r/phillies, Bing News
   └─ render.py    ── génère _site/index.html
   └─ commit + déploiement GitHub Pages
```

Aucune base de données : le fil vit dans `data/items.json`.

## Sources

| Source | Type |
|---|---|
| Phillies Nation, The Good Phight, Crossing Broad | flux RSS |
| NBC Sports Philadelphia, PhillyVoice, The Liberty Line | flux RSS |
| Phuture Phillies, Phillies Minor Thoughts | prospects |
| That Balls Outta Here, MLB Trade Rumors | flux RSS |
| r/phillies | Reddit |
| Bing News (3 requêtes) | presse généraliste |

## Lancer en local

```bash
python3 collect.py && python3 render.py
# puis ouvrir _site/index.html
```

Python 3 uniquement, bibliothèque standard — aucune dépendance à installer.

## Notes techniques

- **User-Agent navigateur obligatoire** : plusieurs sites renvoient 403 ou du HTML aux
  User-Agents de robots (constaté sur Reddit et Phillies Nation).
- **Les liens Bing News sont des redirections**, résolues par `resolve_bing()` (HEAD → 302).
  Google News a été abandonné : ses tokens sont chiffrés et son endpoint de résolution
  refuse les IP de datacenter. Bing répond un vrai 302.
- **Plafond par source** : aucune source ne peut écraser le fil (14 articles pour les flux,
  30 pour la presse) + déduplication par similarité de titres.

## Droits

Titres et extraits appartiennent à leurs auteurs. Cette page n'affiche que des amorces
et renvoie systématiquement à la source. Aucun contenu de paywall.
