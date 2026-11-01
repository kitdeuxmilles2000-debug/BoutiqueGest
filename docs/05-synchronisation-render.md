# Synchroniser la boutique locale vers Render

## Principe

La base SQLite du PC boutique reste la source de vérité. Depuis **Administration > Synchronisation**,
le propriétaire lance un transfert complet des données métier vers PostgreSQL sur Render. Ce transfert
est unidirectionnel; l'application Render est en lecture seule pour les opérations métier.

Les instantanés sont compressés et envoyés en HTTPS avec un jeton Bearer. Render fusionne les lignes
par UUID dans une transaction. Les catégories, unités, catégories de dépenses et caisses par défaut sont
également rapprochées par leur nom/code unique afin d'éviter les doublons créés par l'initialisation
Render. Les données Render qui ne figurent pas dans l'instantané sont conservées.
Une collision de code ou de référence annule l'import entier et apparaît comme une erreur dans l'écran
de synchronisation; aucun remplacement destructif n'est fait.

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

4. Redémarrer le serveur local, se connecter avec le compte propriétaire, ouvrir
   **Administration > Synchronisation** et cliquer **Synchroniser maintenant**.
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

## Utilisation et limites

- Relancer **Synchroniser maintenant** après des changements locaux à publier. Le transfert actuel est
  déclenché manuellement et n'a pas besoin d'Internet pour enregistrer les ventes locales.
- Une nouvelle synchronisation met à jour les UUID déjà importés et ajoute les nouveaux.
- Les suppressions locales ne sont pas répliquées; les lignes déjà présentes sur Render sont conservées
  par le mode fusion.
- Les collisions métier nécessitent de résoudre l'enregistrement concerné sur Render avant de relancer.
- Pour les données volumineuses dépassant la limite de transfert, diviser l'import ou prévoir une
  procédure d'import dédiée plutôt que d'envoyer la base SQLite brute.
- `CLOUD_READ_ONLY=1` bloque les écritures métier sur Render; les connexions, déconnexions et changements
  de mot de passe des comptes cloud restent permis.
