# Synchroniser la boutique locale et Render

## Principe

Le PC boutique lance la synchronisation depuis le bouton de l'en-tête ou **Administration > Synchronisation**.
Le PC récupère l'instantané PostgreSQL de Render, fusionne les données, puis renvoie l'ensemble fusionné.
Les utilisateurs autorisés peuvent donc travailler sur les deux applications; le PC doit être allumé
et connecté pour rapatrier les changements du web.

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

## Configuration initiale

1. Dans Render, créer un **Blueprint** depuis le dépôt GitHub et sélectionner `render.yaml`.
   La configuration installe PostgreSQL, exécute les migrations et crée les données de référence
   ainsi qu'un compte administrateur cloud. Les secrets `SECRET_KEY`, `ADMIN_PASSWORD` et
   `SYNC_API_TOKEN` sont générés par Render.
2. Dans le tableau de bord Render, ouvrir les variables d'environnement du service et noter
   `ADMIN_USERNAME` et `ADMIN_PASSWORD` pour la première connexion cloud. Puis copier la valeur de
   `SYNC_API_TOKEN` pour la configuration du PC local. Ces secrets ne doivent pas être placés dans
   Git ou dans le paquet de mise à jour client.
3. Sur le PC boutique, ajouter au fichier `.env` local les trois paramètres suivants, avec l'URL
   réelle du service Render et le jeton copié :

   ```dotenv
   SYNC_ENABLED=1
   SYNC_REMOTE_URL=https://votre-service.onrender.com/api/sync/snapshot
   SYNC_API_TOKEN=valeur-copiee-depuis-Render
   ```

4. Redémarrer le serveur local et se connecter avec un compte qui possède la permission
  **Gérer la synchronisation**. Cliquer **Synchroniser** dans l'en-tête ou **Synchroniser maintenant**
  dans **Administration > Synchronisation**. Le transfert récupère d'abord les changements Render,
  puis envoie les données fusionnées.
5. Se connecter à l'application Render avec un compte cloud configuré séparément pour consulter les
   données importées.

Le compte local et le compte cloud sont distincts. La synchronisation ne crée pas de compte cloud
utilisable à partir des identifiants locaux.

## Plan Render et conservation des données

Le Blueprint fourni utilise le plan gratuit pour permettre un premier déploiement d'essai. **Il ne
convient pas à la conservation des données d'une boutique** : Render indique que les bases PostgreSQL
gratuites expirent après 30 jours; les services Web gratuits peuvent aussi s'arrêter en cas d'inactivité.
Avant d'importer des données réelles ou de compter sur Render comme copie de sauvegarde, choisissez dans
Render un plan PostgreSQL payant avec conservation des données, puis vérifiez qu'une sauvegarde et une
procédure de restauration sont disponibles. La base SQLite locale reste la référence et doit elle-même
continuer à être sauvegardée.

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
- **Sur Render (PostgreSQL)** : les sauvegardes locales du PC ne couvrent pas la base cloud. Utiliser
  le tableau de bord Render pour exporter la base et vérifier les options de sauvegarde/restauration
  incluses dans le forfait sélectionné. Ne pas compter sur le plan gratuit pour conserver les données
  de la boutique.

## Utilisation et limites

- Cliquer **Synchroniser** après des changements sur le PC ou sur le web. Le transfert est manuel et
  l'application locale continue de fonctionner hors ligne; les changements web seront récupérés au
  prochain transfert.
- Une synchronisation met à jour les UUID déjà importés et ajoute les nouveaux. La dernière date
  `updated_at` détermine la version retenue pour une même ligne.
- Les suppressions sur l'une ou l'autre application ne sont pas répliquées; les lignes déjà présentes
  dans l'autre base sont conservées.
- Les collisions métier nécessitent de résoudre l'enregistrement concerné sur Render avant de relancer.
- Pour les données volumineuses dépassant la limite de transfert, diviser l'import ou prévoir une
  procédure d'import dédiée plutôt que d'envoyer la base SQLite brute.
- `CLOUD_READ_ONLY=0` autorise les opérations métier sur Render. Vérifier cette variable dans le tableau
  de bord Render après le déploiement; une surcharge manuelle peut prévaloir sur `render.yaml`.
