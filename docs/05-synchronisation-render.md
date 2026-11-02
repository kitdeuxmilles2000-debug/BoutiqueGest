# Synchroniser la boutique locale et Render

## Principe

Le PC boutique conserve la base SQLite de référence. Le dépôt contient une copie de démonstration
utilisée au déploiement Render; ce n'est pas le même fichier SQLite partagé en direct. Le bouton du PC
transfère les données par l'API HTTPS et fusionne les lignes par UUID.

Les instantanés sont compressés et échangés en HTTPS avec un jeton Bearer. Les lignes sont fusionnées
par UUID; les catégories, unités, catégories de dépenses et caisses par défaut sont aussi rapprochées
par leur nom/code unique. Pour une même ligne modifiée des deux côtés, la valeur `updated_at` la plus
récente gagne. Gardez l'horloge Windows à l'heure: un décalage d'horloge peut fausser ce choix. Une
collision de code ou de référence annule l'import et apparaît dans l'écran de synchronisation.
Les suppressions ne sont pas propagées; les lignes absentes de l'autre base sont conservées.

Les produits, catégories, unités, fournisseurs, clients, stocks et lots, mouvements, achats, ventes,
paiements, remboursements, caisse, crédits, dépenses, inventaires et taux sont transférés. Les mots de
passe, PIN, e-mails et paramètres d'authentification des comptes locaux ne sont pas transmis. Les noms
des membres du personnel sont conservés dans des comptes miroir désactivés afin de préserver les
références d'auteur des opérations.

## Déploiement Render de démonstration

1. Dans Render, déployer le Blueprint `render.yaml`. Le build applique les migrations au fichier
  `instance/boutiquegest.db` publié dans le dépôt. La réception des snapshots reste protégée par
  `SYNC_API_TOKEN`.
2. Sur le PC boutique, ajouter au fichier `.env` local les trois paramètres suivants, avec l'URL
   réelle du service Render et le jeton copié :

   ```dotenv
   SYNC_ENABLED=1
   SYNC_REMOTE_URL=https://votre-service.onrender.com/api/sync/snapshot
   SYNC_API_TOKEN=valeur-copiee-depuis-Render
   ```

3. Redémarrer le serveur local et se connecter avec un compte qui possède la permission
  **Gérer la synchronisation**. Cliquer **Synchroniser** dans l'en-tête ou **Synchroniser maintenant**
  dans **Administration > Synchronisation**. Le transfert récupère d'abord les changements Render,
  puis envoie les données fusionnées.
4. Se connecter à Render avec les identifiants présents dans la copie SQLite publiée.

Cette publication inclut volontairement la base SQLite complète, y compris les comptes, leurs
empreintes de mot de passe et les données métier, pour une vérification temporaire demandée par le
propriétaire. Le dépôt GitHub est public: ces données sont accessibles à tous. Supprimer le fichier
dans une future version ne supprimera pas les anciennes copies de l'historique Git.

## Limites de conservation

Le service Render gratuit utilise un système de fichiers éphémère. Le fichier publié sert de copie
initiale, mais les écritures faites en ligne ne sont pas conservées de manière fiable lors d'un
redémarrage ou d'un nouveau déploiement. Render reste donc en lecture seule pour cette démonstration.
Pour une base SQLite en ligne durable, un disque persistant payant est nécessaire; il s'agira d'une
copie distincte synchronisée avec le PC, pas d'un fichier partagé par GitHub.

## Sauvegardes

- **Sur le PC boutique (SQLite)** : l'installation crée une tâche Windows quotidienne à 02:00.
  Elle utilise la commande `flask backup-db`, vérifie l'intégrité de la copie et conserve les
  30 sauvegardes les plus récentes. Si l'ordinateur est éteint à l'heure prévue, la tâche est
  configurée pour démarrer à la prochaine occasion. Les fichiers sont dans `backups/` à la racine
  de l'installation; le journal de la tâche est `backups/automatic_backup.log`.
- **Sauvegarde manuelle locale** : dans **Administration > Sauvegardes**, cliquer
  **Créer une sauvegarde maintenant**. La copie apparaît dans la liste et peut être téléchargée.
- **Points de restauration** : les instantanés manuels de l'historique restent disponibles depuis
  cette même page. La restauration exige le mot de passe propriétaire et un motif.
- **Sur Render (copie de démonstration)** : la base est réinitialisée depuis le fichier du dépôt au
  prochain build et le disque du service gratuit est éphémère. Ne pas y enregistrer de nouvelles données
  métier à conserver.

## Utilisation et limites

- Cliquer **Synchroniser** après des changements sur le PC. Le transfert est manuel; l'application
  locale continue de fonctionner hors ligne.
- Une synchronisation met à jour les UUID déjà importés et ajoute les nouveaux. La dernière date
  `updated_at` détermine la version retenue pour une même ligne.
- Les suppressions ne sont pas répliquées; les lignes déjà présentes dans l'autre base sont conservées.
- Les collisions métier nécessitent de résoudre l'enregistrement concerné sur Render avant de relancer.
- Pour les données volumineuses dépassant la limite de transfert, diviser l'import ou prévoir une
  procédure d'import dédiée plutôt que d'envoyer la base SQLite brute.
- `CLOUD_READ_ONLY=1` garde la copie de démonstration Render en consultation seule.
