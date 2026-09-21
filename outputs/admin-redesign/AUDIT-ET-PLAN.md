# Black Market — audit web et plan de refonte

Date : 20 septembre 2026. Périmètre : interfaces web, routes d’administration et leurs contrats de données. Le code des conversations du bot et les services métier ne sont pas modifiés. Ce document est un audit du dépôt local, pas une certification du déploiement ou des fournisseurs externes.

## 1. Inventaire des sites

| Surface | Source | Constat |
|---|---|---|
| Administration principale | `admin-ui/src/App.jsx`, `AdminPages.jsx`, `styles.css` | React/Vite, treize rubriques, lecture JSON et écritures vers `/admin`. Base fonctionnelle importante à conserver. |
| Administration historique | `api/dashboard.py` | Grand template Python conservé à `/admin-legacy`. Deux interfaces à maintenir ; retrait seulement après couverture des parcours de secours. |
| Vitrine publique | `api/public_site.py` | Page adaptative avec catalogue et support via Telegram, contrôle `/health` toutes les 15 secondes. |
| Conditions publiques | `assets/terms.html`, route `/terms` dans `railway_server.py` | Page statique, sommaire et liens Telegram. Contenu non relié aux paramètres légaux du panneau. |
| Site de conditions séparé | `black-market-terms-site/dist/index.html` | Copie identique en contenu à la page précédente ; seule une ligne vide finale diffère. Dépôt imbriqué enregistré comme gitlink sans correspondance `.gitmodules`. Livraison à clarifier. |
| Storefront | `storefront-ui/` | Seulement `node_modules` dans le dossier local inspecté : aucune application source exploitable trouvée. Ne pas présenter comme une boutique web opérationnelle. |
| API d’administration | branches web de `api/webhook.py`, `app/web/dashboard_api.py` | Routes protégées, filtres/pagination, actions métier existantes. Ne pas dupliquer ces règles dans React. |

## 2. Défauts établis dans les sources

| Priorité | Preuve | Conséquence | Décision |
|---|---|---|---|
| P0 | `App.jsx`, `RevenueChart`, ligne 195 : multiplication du revenu hebdomadaire par des coefficients fixes | La courbe journalière représente des chiffres inventés. | Retirer la courbe actuelle ; afficher les agrégats réels jusqu’à disponibilité d’une série datée côté serveur. |
| P0 | `App.jsx`, `Sidebar` : texte « Bot connecté » constant | Un incident peut apparaître comme un état sain. | Lire `/admin/api/telegram-health`, distinguer inconnu, sain, dégradé et échec. |
| P1 | `vite.config.js` : proxy seulement pour `/admin/api`, alors que les mutations ciblent `/admin` | L’environnement Vite ne relaie pas les actions d’administration vers Python. | Ajouter une règle précise pour les POST `/admin`, vérifier navigation SPA et fichiers `/admin-v2/`. |
| P1 | GET `/admin/api/data` réécrit `shop_name` depuis l’environnement et `currency` depuis une constante, alors que `save_settings` les écrit en base | Valeurs potentiellement incohérentes après enregistrement. | Définir une source de vérité et vérifier un cycle enregistrer → relire → afficher. |
| P1 | `SettingsPage` appelle `onHealthCheck("telegram")`, qui exécute `repair_telegram_webhook` | Le bouton « Telegram » modifie le webhook au lieu d’effectuer un simple diagnostic. | Séparer « Tester la connexion » (GET) et « Réparer le webhook » (POST explicite). |
| P1 | `SearchDialog` filtre uniquement `data.orders/users/services/tickets` et ouvre une rubrique | Recherche limitée au lot chargé et absence d’ouverture de la fiche trouvée. | Recherche serveur paginée avec navigation vers l’entité exacte. |
| P1 | `loadData` ignore visuellement les erreurs de rafraîchissement en arrière-plan | Les anciennes données restent visibles sans avertissement de fraîcheur. | Horodatage de synchronisation et bandeau « données anciennes », bouton réessayer. |
| P1 | `save_settings` enregistre `terms_message/privacy_message`, `/terms` lit un fichier | Modifier le texte légal dans le panneau ne publie pas la page web. | Distinguer messages du bot et pages publiées ; éditeur versionné avec aperçu et publication. |
| P1 | `dashboard_write_token` est stable, et `_dashboard_authorized` l’accepte seul | Ce jeton est en pratique un accès administrateur réutilisable, pas seulement un jeton anti-CSRF. | Session nominative révocable ; anti-CSRF lié à la session ; contrôle des autorisations côté serveur. |
| P2 | `api/public_site.py` : `lang="en"` pour un texte français ; footer sans lien `/terms` | Langue déclarée incorrecte et page légale peu accessible. | Corriger la langue, ajouter conditions et confidentialité quand cette dernière est réellement publiée. |
| P2 | Vitrine initialement « En ligne / Opérationnel » avant le résultat de `/health` | État positif non encore vérifié ; santé HTTP ne prouve pas à elle seule le bon fonctionnement de Telegram. | État initial « Vérification » et description exacte du service mesuré. |
| P2 | Login partagé `admin` et mot de passe unique dans la route de connexion | Pas de comptes nominatifs ni de rôles démontrés dans le panneau. | Ajouter propriétaire, opérateur, support, finance, lecture seule et gestion des sessions. |

Les API fournisseurs et l’IA sont conditionnées à leur configuration. Une clé absente ne prouve pas qu’une fonction est cassée : conserver la configuration et masquer l’action opérationnelle tant qu’elle n’est pas disponible. Aucun appel commercial, remboursement, crédit, envoi Telegram ou changement de production n’a été exécuté pour cet audit.

## 3. Organisation proposée

Nom du template : **Black Market / Control Room**. Une interface de travail sobre : fond ivoire, navigation anthracite, accent citron repris des conditions actuelles, typographie système nette, chiffres tabulaires et tables lisibles. Thème sombre complémentaire avec les mêmes contrastes et composants.

| Groupe | Pages et outils |
|---|---|
| Pilotage | Vue d’ensemble, file des actions urgentes, rapports datés et centre des alertes |
| Commerce | Commandes, catalogue, inventaire, clients, garanties et demandes après-vente |
| Finance | Dépôts, portefeuille et mouvements, remboursements, demandes de retrait, rapprochement |
| Bots et intégrations | Bot configuré, état Telegram, maintenance, messages, fournisseurs, clés clients API, connecteurs externes |
| Contenu | Accueil, conditions, confidentialité, liens de support, langues, versions publiées |
| Administration | Explorateur de données, journal, comptes et droits, sessions, exports et sauvegardes |

La navigation de la maquette illustre cette architecture avec des données fictives explicitement signalées. Elle ne constitue pas l’implémentation des nouvelles API.

## 4. Matrice conserver / réparer / ajouter / retirer

**Conserver et mieux présenter :** commandes et livraison manuelle, notes, remboursement via service métier, services/offres, import de stock, masquage/révélation du stock, portefeuille, modération client, approbation des dépôts, tickets et réponses, clés API, produits fournisseurs, connecteurs, journal et annulation des actions admissibles. Les handlers existent ; la disponibilité réelle des intégrations reste à tester sur environnement de recette.

**Réparer avant redesign :** courbe fictive, état Telegram constant, proxy d’écriture, cohérence des paramètres, recherche, erreurs de synchronisation, diagnostic/réparation et publication des textes web.

**Ajouter :** vues sauvegardées, colonnes personnalisables cohérentes, export filtré, liens directs vers les fiches, historique complet client, tâches de traitement, centre des incidents, suivi des retraits, garanties, éditeur web versionné, accès nominatifs, sessions révocables et couverture des données actuellement hors interface.

**Retirer de l’interface active :** statistiques fabriquées, assertions de disponibilité sans preuve, raccourcis vers pages inexistantes. Ne supprimer le legacy qu’après validation de sa couverture ; ne supprimer aucun enregistrement métier pour nettoyer une interface. IA rangée dans les outils optionnels selon disponibilité, pas comme rubrique principale imposée.

## 5. Contrôle de la base et des bots

Le propriétaire doit pouvoir administrer toutes les ressources métier depuis le site. Cela demande une matrice explicite « ressource → lecture → création → modification → archivage → export → permission → trace d’audit ».

Pour commandes, soldes, paiements et livraisons, les mutations passent par les services existants pour préserver réservations, écritures financières et notifications. L’explorateur fournit collections autorisées, schéma de champs, filtres, pagination, relations et export masqué. Les champs secrets ne sont jamais renvoyés par défaut ; les valeurs révélées font l’objet d’une action dédiée. Une prévisualisation liste les enregistrements concernés avant toute action de masse.

Les nouveaux endpoints web nécessitent validation serveur, idempotence pour argent/livraison, contrôle de concurrence pour édition, journal avec acteur et ancienne/nouvelle valeur, limites de pagination et erreurs structurées. Un affichage ou bouton conditionnel côté React ne remplace jamais une permission côté serveur.

**Limite multi-bot :** les surfaces inspectées utilisent un seul `bot_username` configuré. Un sélecteur de bots ne suffirait pas à isoler plusieurs boutiques. La première livraison contrôle le bot existant. Pour plusieurs bots, il faut une étude dédiée des identifiants, index, collections, droits, secrets, tâches et webhooks ; cette phase dépasserait une refonte exclusivement frontend et pourrait nécessiter une migration des services du bot. Ne pas promettre cette capacité sous la contrainte actuelle sans cette étude.

## 6. Comportements et animations

- Page : entrée discrète de 160–220 ms, uniquement opacité et translation courte.
- Navigation : onglet actif, fil d’Ariane, lien direct et historique du navigateur.
- Tables : recherche serveur, filtres synchronisés dans l’URL, pagination, sélection explicite, vue mobile dédiée.
- Détails : panneau latéral pour lecture/édition rapide, conservation du contexte de liste.
- Mutations : état d’envoi, résultat serveur, erreur conservant la saisie, protection contre double clic ; pas de succès financier optimiste.
- Données : squelettes, état vide utile, erreur explicite, dernière synchronisation, distinction zéro/inconnu.
- Accessibilité : clavier complet, focus visible, restitution du focus, Échap, dialogues accessibles, contraste et réduction des animations via `prefers-reduced-motion`.
- Pages légales : même identité visuelle, sommaire ancré, date/version, impression lisible, liens de support. Le contenu juridique n’est pas réécrit ni validé juridiquement par cet audit technique.

## 7. Architecture de réalisation

Conserver React/Vite existant. Extraire progressivement `components/`, `features/orders`, `catalog`, `finance`, `customers`, `support`, `bots`, `content`, `access` et `data`. Centraliser le client HTTP, les erreurs, les permissions et l’invalidation des données. Découper les très grands fichiers actuels par domaine ; charger les pages à la demande. Déplacer progressivement les seules routes web vers des modules d’administration sans changer les traitements du bot.

Contrats nouveaux proposés : `/admin/api/capabilities`, `/metrics?from=&to=&timezone=`, `/search?q=&type=&page=`, `/content/pages`, `/sessions`, `/admin-users`, `/data/collections`, `/exports`. Ce sont des contrats à construire, pas des endpoints disponibles aujourd’hui. Le diagnostic Telegram existant est réutilisable immédiatement.

## 8. Plan de livraison et critères de sortie

| Lot | Livrable | Validation nécessaire |
|---|---|---|
| 0 — fiabilité | Corrections P0/P1, matrice des actions et disponibilité | Courbes issues de données datées, erreurs visibles, test POST Vite, paramètres persistants |
| 1 — socle visuel | Navigation groupée, composants, tables, panneaux, thèmes | Mobile 390 px, tablette, desktop ; clavier, focus, animations réduites |
| 2 — opérations | Migration commandes/catalogue/stock/clients/finance/support | Parcours complets sur base isolée ; contrôle des doubles opérations et erreurs |
| 3 — administration | Droits, sessions, audit enrichi, explorateur, exports | Refus serveur pour rôle interdit ; export masqué ; contrôle de concurrence |
| 4 — contenu et bots | Éditeur de pages, publication versionnée, diagnostics et configuration | Aperçu → publication → lecture publique cohérente ; indisponibilité correctement représentée |
| 5 — livraison | Build reproductible, recette, déploiement et retour arrière | Tests API, tests navigateur avec données de recette, absence de secrets dans bundle, validation des intégrations configurées |

La suppression définitive d’une ancienne option exige un motif documenté, son remplacement éventuel et un contrôle des usages. Une maquette réussie n’est pas une validation de l’accès à la base, des paiements ou de Telegram.

## 9. Validation de cet audit

Les résultats des commandes de build et des tests ciblés sont consignés dans `VALIDATION.md`. La maquette `control-room.html` fonctionne seule et utilise exclusivement des données de démonstration. Les tests du dépôt utilisent MongoDB simulé ; aucun test connecté de production n’est revendiqué.
