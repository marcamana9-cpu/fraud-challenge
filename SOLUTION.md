# Solution proposée

## Objectif

La solution met en place un détecteur de fraude robuste, explicable et prudent. Elle cherche à repérer les signaux forts de fraude sans bloquer inutilement les transactions légitimes.

## Approche technique

Le moteur `detect_fraud` attribue un score de risque entre `0.0` et `1.0` à chaque transaction. Le verdict est considéré comme suspect à partir de `0.75`.

Les principaux signaux utilisés sont :

- montant manquant, invalide, nul ou négatif ;
- champs essentiels manquants ;
- montant très supérieur aux habitudes du client dans la même devise ;
- changement de pays impossible ou très rapide ;
- fréquence inhabituelle de transactions rapprochées ;
- doublons d'identifiant ou transactions répétées à l'identique ;
- paiement en ligne de montant élevé.

## Gestion des cas limites

La fonction est conçue pour ne pas planter si les données sont imparfaites :

- transaction mal formée ;
- timestamp absent ou invalide ;
- montant `None`, non numérique, infini ou non exploitable ;
- pays vide ou écrit avec une casse différente ;
- ordre chronologique désordonné dans le fichier.

## Interface de démonstration

L'interface Streamlit transforme les résultats en tableau de bord lisible :

- synthèse exécutive du lot analysé ;
- alertes prioritaires avec score et action recommandée ;
- tableau filtrable par client ;
- résumé des clients à surveiller ;
- explication simple des règles de décision.

Commande de lancement :

```bash
streamlit run app.py
```

## Résultat

Les tests publics passent localement : `11/11`.

