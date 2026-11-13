# Pont éclair ACM → NotebookLM : index local, recherche rapide et export

Ce pont prend une archive texte locale et fabrique un index de liens interrogeable par URL exacte, domaine ou mots-clés. Il exporte ensuite les résultats pertinents dans un fichier Markdown importable manuellement dans NotebookLM.

## Modèle mathématique et logique

Pour chaque lien `u`, le parseur conserve une fiche `r(u)` avec sa catégorie, ses occurrences, son contexte textuel et son offset dans l’archive. Un index inversé associe chaque terme aux fiches qui le contiennent. La recherche combine un score lexical de type BM25 avec une priorité déterministe pour URL exacte et domaine :

`Score(u,q) = Score_lexical(u,q) + bonus_URL_exacte + bonus_domaine`.

Ce score accélère le repérage; il n’indique ni fiabilité ni vérité. L’extraction et le tri sont testables sur des exemples annotés. Un changement d’entrée est traçable par SHA-256. Même fichier, version de programme et configuration donnent le même index sérialisé.

## Utilisation avec `texte 105.txt`

Depuis la racine du dépôt :

```bash
python3 acm_bridge.py build "texte 105.txt" --index acm-index.json
python3 acm_bridge.py search acm-index.json "Willow qubit"
python3 acm_bridge.py search acm-index.json "https://github.com/NickelRamQc94"
python3 acm_bridge.py export acm-index.json "équation algorithme Willow" --limit 40 --out NOTEBOOKLM-ACM-EXPORT.md
```

Pour lancer les tests :

```bash
python3 -m unittest discover -s tests -v
```

## Transfert à Gemini NotebookLM

Le script ne peut pas se connecter à ton compte ni téléverser automatiquement une source. Il crée `NOTEBOOKLM-ACM-EXPORT.md`; relis-le, enlève ce qui ne doit pas être partagé, puis importe/colle ce fichier manuellement dans le notebook. C’est le pont pratique entre l’archive et le notebook : l’index local réduit la recherche à un sujet ou à une adresse, et l’export contient les liens avec leur contexte et leur provenance.

## Limites et sécurité

- Aucun accès au profil Chrome, à Drive, à GitHub ou à des comptes; aucune requête réseau.
- Aucun code découvert dans les textes n’est exécuté.
- Les URL restent `user_supplied_unverified`; le script ne teste ni disponibilité ni permissions.
- Les extraits sont des fenêtres de texte autour des liens; ils peuvent être incomplets. Les liens non littéralement présents (URL masquées dans des documents binaires ou liens Markdown sans URL visible) ne sont pas reconstruits.
- Les fichiers générés peuvent contenir des URL privées ou sensibles. Ils sont locaux par défaut : ne pas les publier avant revue.
- La note exportée est une sélection de recherche, pas une sauvegarde intégrale de toute l’archive.
