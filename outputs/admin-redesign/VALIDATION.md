# Vérifications — 20 septembre 2026

- Build de l’interface existante : `npm.cmd run build -- --outDir ../outputs/admin-audit-build` — réussi, Vite 8.2.1. Sortie isolée ; `admin-ui/dist` inchangé.
- Tests ciblés : `python -m pytest tests/test_dashboard_api.py tests/test_railway_server.py -q` — **40 réussis**, 11,18 secondes. Base MongoDB simulée par les fixtures du dépôt.
- Maquette ouverte dans le navigateur intégré : affichage desktop inspecté visuellement.
- Navigation vers les commandes, recherche « Camille », fiche #1048, fermeture et recherche sans résultat : vérifiées.
- Filtre « Livrée » : deux commandes de démonstration (#1047 et #1046).
- Changement du thème clair/sombre : vérifié.
- Viewport mobile 390 × 844 : ouverture du menu et retour à l’accueil vérifiés ; aucun débordement horizontal de la page constaté. Dimensions temporaires réinitialisées après le contrôle.
- Console : aucune erreur JavaScript capturée pendant ces parcours.
- Export CSV : implémenté pour les données fictives filtrées, téléchargement non vérifié dans cette passe.

Les vérifications navigateur concernent la maquette, pas une session d’administration de production. La présence des handlers dans les sources ne garantit pas que chaque fournisseur, paiement ou action Telegram fonctionne sur le déploiement réel.

Livrables ajoutés uniquement sous `outputs/admin-redesign/`. Aucun changement du code du bot, aucune suppression de fonctionnalité dans le panneau existant et aucune publication. Les défauts identifiés restent à corriger lors de l’implémentation du plan.

Prévisualisation locale : `python -m http.server 8769 --bind 127.0.0.1 --directory outputs/admin-redesign`, puis ouvrir `http://127.0.0.1:8769/control-room.html`. Le fichier HTML peut également être ouvert directement.
