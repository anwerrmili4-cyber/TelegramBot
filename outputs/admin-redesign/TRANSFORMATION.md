# Refonte structurelle — 21 septembre 2026

Cette passe répond à la demande de transformation au-delà du premier habillage.

## Structure remplacée

- Ancien accueil supprimé du composant App, remplacé par `WorkspaceHome.jsx` : introduction, indicateurs regroupés, file de travail, onglets performance/commandes récentes, accès métier et contexte boutique.
- Navigation organisée en trois groupes : espace de travail, catalogue/finance et administration. Barre supérieure allégée ; réparation du webhook déplacée dans les paramètres.
- Commandes : files rapides de traitement, analyses repliables, conservation des vues cartes/tableau/kanban et des actions métier existantes.
- Catalogue : résumé des collections/offres/sélections et filtre par collection, tout en conservant les outils de gestion et actions groupées existants.
- Fournisseurs : annuaire latéral et catalogue principal ; diagnostics, clés clients et connecteurs dans des rubriques séparées. Sélection initiale d’un fournisseur configuré, actions désactivées pour ceux non configurés. Protection contre une réponse de catalogue devenue obsolète après changement de fournisseur.
- Nouvelle composition desktop/mobile dans `workspace.css`, complémentaire des tokens du thème et des styles des outils métier.

## Recette

- Build de production régénéré avec succès.
- 60 tests Python et 5 tests frontend réussis.
- Navigateur : nouvel accueil, navigation groupée, onglets des fournisseurs, liste de produits utilisés/non utilisés, affichage mobile 390 × 844 sans débordement horizontal ; aucune erreur console capturée.
- Prévisualisation enrichie avec deux produits et trois fournisseurs explicitement fictifs. Les POST y restent refusés. Aucun achat, paiement ni message Telegram exécuté.

## Périmètre réel

Les pages accueil, commandes, catalogue et fournisseurs sont restructurées. Les autres pages héritent du nouvel environnement visuel mais conservent leurs formulaires métier. Cette passe ne crée ni gestion multi-bot ni système de rôles, et ne modifie pas les pages publiques ou le contenu juridique. Les limites de Safari physique et du déploiement indiquées dans `IMPLEMENTATION.md` restent applicables.
