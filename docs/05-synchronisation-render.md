# Synchroniser la boutique locale, GitHub et Render

## Principe

Le PC boutique garde sa base SQLite locale. Un instantané compressé des données métier est enregistré
dans un fichier sur une branche GitHub dédiée (`boutiquegest-data`), distincte de la branche de code
surveillée par Render. Le fichier est échangé via l'API HTTPS de GitHub; la base SQLite brute n'est pas
publiée.

Le PC et Render vérifient GitHub à l'ouverture des pages, au plus une fois toutes les 30 secondes par
processus. Une écriture réussie dans l'application republie l'instantané automatiquement; le bouton
**Synchroniser GitHub** force une synchronisation immédiate. Les données sont fusionnées par UUID et,
pour une même fiche, la version avec `updated_at` le plus récent est retenue. Une collision de code ou
de référence annule l'import et apparaît dans l'écran de synchronisation. Les suppressions physiques
détectées depuis la dernière synchronisation sont répliquées par des marqueurs conservés dans le fichier GitHub.

Les tables métier définies par `SNAPSHOT_TABLES` sont transférées. Les mots de passe, PIN, e-mails et
paramètres d'authentification des comptes ne sont pas inclus; les noms du personnel sont conservés
dans des comptes miroir désactivés afin de préserver les références d'auteur. Un dépôt GitHub privé
est obligatoire : les instantanés peuvent contenir des données commerciales et personnelles.

## Déploiement Render de démonstration

1. Utiliser un dépôt GitHub **privé** dédié aux données ou un dépôt privé autorisé. Créer un jeton
   Fine-grained limité à ce dépôt, avec **Contents: Read and write**. Le code refuse les dépôts publics.
2. Dans Render, déployer le Blueprint `render.yaml`, puis renseigner `GITHUB_SYNC_REPOSITORY` et
   `GITHUB_SYNC_TOKEN` dans les variables secrètes du service. Render est configuré en lecture/écriture.
3. Sur le PC boutique, copier `.env.example` vers `.env` et renseigner :

   ```dotenv
   GITHUB_SYNC_ENABLED=1
   GITHUB_SYNC_REPOSITORY=proprietaire/depot-prive
   GITHUB_SYNC_TOKEN=jeton-github
   GITHUB_SYNC_BRANCH=boutiquegest-data
   GITHUB_SYNC_PATH=sync/boutiquegest-snapshot.json.gz
   GITHUB_SYNC_POLL_SECONDS=30
   ```

4. Redémarrer l'application locale. Le premier changement enregistré ou un clic sur le bouton de
   synchronisation initialise la branche et publie le premier instantané. Le compte doit avoir la
   permission **Gérer la synchronisation** pour utiliser le bouton.

## Limites de conservation

Le service Render gratuit utilise un système de fichiers éphémère; il récupère donc l'instantané
GitHub à nouveau après un redémarrage. Chaque publication crée une version de fichier sur la branche
de données, sans déclencher le déploiement du code. GitHub limite les fichiers de l'API Contents; le
fichier compressé est limité à 900 Ko. Les changements simultanés sont retentés jusqu'à trois fois.

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
- **Sur Render** : le disque du service gratuit est éphémère; les données métier sont rechargées depuis
  l'instantané GitHub au prochain accès après redémarrage. Vérifier également l'historique de la branche
  de données pour conserver les versions publiées.

## Utilisation et limites

- Sans Internet, l'application locale continue de fonctionner; la synchronisation reprend à la
  prochaine ouverture de page ou écriture lorsque la connexion revient.
- Une synchronisation met à jour les UUID déjà importés, ajoute les nouveaux et propage les
  suppressions détectées depuis la dernière synchronisation.
- Les collisions métier nécessitent de résoudre l'enregistrement concerné avant de relancer.
- Ne pas utiliser cette synchronisation avec des données réelles tant que le dépôt GitHub n'est pas
  privé. La détection des suppressions hors ligne dépend des dates `created_at` et de la dernière
  synchronisation; vérifiez les conflits si plusieurs PC restent déconnectés longtemps.
