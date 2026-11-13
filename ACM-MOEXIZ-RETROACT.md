# ACM / MoExiZ / RetroAct — prototype reproductible

Ce prototype transforme un fichier texte local choisi par l’utilisateur en index de liens, statistiques, rapport Markdown, manifeste SHA-256 et comparaison RetroAct facultative.

## Sens des noms

- **ACM (Active Dynamic Chrome Memory)** : ici, un index documentaire local et versionné. Ce script n’accède ni au profil Chrome, ni aux comptes, ni aux ressources privées.
- **MoExiZ (Mixtures of Expertises)** : prononcé avec la terminaison anglaise « -iz », selon le nom donné par le propriétaire. Dans ce prototype, c’est un routage explicable par comptage de mots-clés vers quatre rôles. Ce n’est pas un réseau neuronal entraîné ni un système multi-agent déployé.
- **RetroAct** : diff en lecture seule entre le nouvel index et un ancien `sources.json`; aucune source n’est modifiée automatiquement.

## Utilisation

Exécuter localement depuis la racine du dépôt :

```bash
python3 acm_moexiz_retroact.py "texte 105.txt" --out acm-output
```

Comparer avec une exécution précédente :

```bash
python3 acm_moexiz_retroact.py "texte 105.txt" --out acm-output-v2 --previous acm-output/sources.json
```

Les sorties sont `sources.json`, `report.md`, `retroact-diff.json` et `manifest.json`. Les fichiers produits sont locaux; les données extraites ne doivent pas être poussées dans un dépôt public sans revue des liens, autorisations et informations sensibles.

## Tests et contrôles

Python standard seulement, aucune dépendance externe :

```bash
python3 -m unittest discover -s tests -v
```

La suite couvre l’extraction/déduplication, la classification, le rejet d’URL contenant des identifiants, la stabilité des résultats, le diff et les empreintes des fichiers générés.

## Contrat et limites

- Entrée attendue : texte UTF-8 (un éventuel BOM est accepté).
- Seuls les liens `http://` et `https://` sont extraits; les liens masqués sans URL littérale ne peuvent pas être reconstruits.
- Les hôtes et schémas sont normalisés en minuscules; les chemins, paramètres et fragments sont préservés.
- Aucune requête réseau, aucun clone Git, aucune exécution du contenu extrait, aucune connexion à Chrome/Google/GitHub.
- Le statut de chaque lien reste `user_supplied_unverified`; le script ne teste ni disponibilité ni contenu.
- Les statistiques décrivent les octets analysés et les correspondances du parseur. Elles ne prouvent pas l’exhaustivité au-delà de cette définition.
- Le routage MoExiZ est une heuristique transparente et falsifiable, pas une probabilité de vérité. Les poids sont des scores normalisés de comptage lexical.
- Même entrée, version du script, configuration et baseline donnent des sorties déterministes. SHA-256 permet de comparer l’intégrité des octets générés, pas leur vérité ou leur sûreté.
- Le script ne prétend pas avoir analysé ni validé lui-même `texte 105.txt`; l’utilisateur fournit le fichier local à traiter.
