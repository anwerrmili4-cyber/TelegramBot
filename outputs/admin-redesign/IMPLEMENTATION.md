# Control Room — implementation, 21 septembre 2026

Cette livraison remplace le stade de simple maquette pour le panneau : les changements sont intégrés dans `admin-ui`, avec un build de production régénéré. Aucune publication n’a été effectuée.

## Réalisé

- Identité ivoire, anthracite et citron, thèmes clair/sombre, transitions respectant la réduction des animations.
- Centre de pilotage : priorités issues du résumé serveur, favoris enregistrés sur l’appareil, diagnostics Telegram/Binance/Bybit déclenchés explicitement.
- Explorateur de cinq ressources métier : commandes, clients, inventaire masqué, tickets, dépôts. Recherche/filtres/pagination via les API existantes ; sauvegarde du type et du statut d’une vue ; export CSV limité à la page et aux colonnes affichées.
- Mode téléphone `/admin/phone`, navigation inférieure, marges iOS, tailles tactiles, champs de saisie 16px, commandes en cartes par défaut sur petit écran.
- Dialogues de formulaire natifs : focus modal, fermeture Échap, défilement interne et restitution du contexte.
- Suppression de la courbe de revenus fabriquée ; utilisation de la série quotidienne fournie par l’API commandes. UTC et date de création explicités.
- Suppression du faux état « Bot connecté », indicateur de synchronisation et erreurs de lecture visibles.
- Test Telegram séparé de la réparation du webhook. Le bouton explicitement nommé « Réparer Telegram » conserve l’action existante.
- Routes directes des nouveaux écrans et des pages IA/clients API, proxy Vite des POST corrigé et testé.
- Aucune modification des conversations ou traitements métier du bot. Dans `api/webhook.py`, seule la liste des routes SPA est étendue.

## Vérifié

- Build Vite réussi, assets `dist` mis à jour.
- 60 tests Python ciblés réussis : dashboard API, HTTP, séparation des surfaces Railway.
- 5 tests frontend réussis : protection CSV, colonnes exportées, session expirée, erreurs serveur et routage réel du proxy Vite.
- Recette navigateur avec données synthétiques isolées : mode téléphone à 390 × 844, navigation inférieure, cartes, ouverture de commande #1048, fermeture Échap, explorateur mobile, filtre Livrée, enregistrement/restauration du filtre, résultat vide et export désactivé.
- Inspection desktop à la taille par défaut : aucun débordement horizontal ; aucune erreur console capturée sur ces parcours. Taille temporaire du navigateur réinitialisée.

## Limites explicites

- Tests responsive réalisés dans le navigateur disponible, pas dans Safari sur un iPhone physique. La recette iOS matérielle, dont clavier et téléchargement CSV, reste nécessaire.
- Les diagnostics des fournisseurs réels et les écritures financières/Telegram n’ont pas été exécutés. Le serveur de prévisualisation refuse toute écriture et affiche son statut de démonstration.
- L’explorateur couvre cinq ressources et permet leur consultation ; il ne fournit pas un éditeur arbitraire de toute la base. Les modifications restent dans les outils métier existants.
- Les comptes nominatifs, rôles, gestion multi-bot et publication versionnée des pages légales du plan initial restent à développer. Le contenu et le déploiement des sites légaux n’ont pas été modifiés dans cette livraison.
- Les favoris et la vue sauvegardée sont propres au navigateur, sans synchronisation entre appareils.

Prévisualisation sur cet ordinateur : `http://127.0.0.1:8770/admin/phone`. Cette adresse loopback n’est pas accessible depuis un téléphone distinct. L’usage sur iPhone demandera l’adresse HTTPS du déploiement, après livraison de ces fichiers.
