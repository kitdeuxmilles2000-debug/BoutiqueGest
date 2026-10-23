# BoutiqueGest — 02 · Architecture technique

> Phase 2 — Conception. Décrit l'architecture cible : **serveur local prioritaire**, application
> **web responsive**, **synchronisation distante idempotente**, **sécurité** et **sauvegardes**.

---

## 1. Vue d'ensemble

```
        ┌──────────────────────── BOUTIQUE (réseau local / Wi-Fi) ───────────────────────┐
        │                                                                                 │
        │   PC SERVEUR LOCAL  ── Flask (API + UI web) ── SQLite ── sauvegardes locales      │
        │        ▲                                                                        │
        │        │  HTTP(S) LAN                                                            │
        │        ├──────────────▶  Tablettes (caisse, stock)                              │
        │        ├──────────────▶  Smartphones (consultation / vendeur)                   │
        │        └──────────────▶  PC bureau (gérant / propriétaire)                      │
        │                                                                                 │
        │   [File de synchronisation]  [Journal d'audit]  [File d'e-mails]                │
        └───────────────────────────────┬─────────────────────────────────────────────────┘
                                        │  HTTPS/TLS  (dès qu'Internet est disponible)
                                        ▼
        ┌───────────────────────── SERVEUR DISTANT (VPS) ────────────────────────────────┐
        │  API de synchronisation  ·  Base distante (agrégat/backup)                      │
        │  Stockage chiffré des sauvegardes  ·  Service SMTP (rapports & alertes)         │
        └─────────────────────────────────────────────────────────────────────────────────┘
```

**Principe** : le **serveur local est la référence** pour toutes les opérations de la boutique.
Internet ne sert qu'à **répliquer** et **sauvegarder** — jamais à conditionner une vente.

---

## 2. Stack technique

| Couche | Choix | Remarque |
|---|---|---|
| Langage | **Python 3.12+** | — |
| Web | **Flask + Jinja2 + Bootstrap 5** | UI responsive premium |
| ORM | **SQLAlchemy 2.x + Alembic** | migrations versionnées |
| Base locale | **SQLite (mode WAL)** | écrans < 2 s, transactions fiables |
| Base distante | **PostgreSQL** (agrégat/backup) | séparée de la base de travail locale |
| Tâches planifiées | **APScheduler** | sauvegardes, e-mails, alertes, sync |
| Rapports | **openpyxl** (Excel), **WeasyPrint** (PDF) | totaux identiques à l'écran |
| Sécurité | **Werkzeug/bcrypt + argon2**, **itsdangerous**, **Flask-WTF (CSRF)** | API et UI |
| E-mails | **Flask-Mail** + file d'attente locale | SMTP côté serveur uniquement |

> Décision de conception : **Application Web progressive (PWA)** pour l'usage tablette/smartphone
> (fonctionne sur le LAN ; service worker pour la consultation hors ligne légère).

---

## 3. Mode local (boutique)

- Le serveur local continue de servir **ventes, caisse, stock, réceptions** sans Internet.
- Chaque opération est **écrite durablement (commit SQLite en WAL)** **avant** de confirmer à l'utilisateur.
- Toutes les écritures financières/stock sont **transactionnelles** : pas d'état partiellement enregistré.
- **Coupure de courant** : écriture atomique + `PRAGMA synchronous=FULL` + vérification d'intégrité au
  redémarrage + **onduleur recommandé**.
- Les appareils du LAN n'ont besoin que du réseau local.

---

## 4. Synchronisation distante (idempotente)

Chaque opération génère un **événement de synchronisation** :

```
SyncEvent {
  id (UUIDv4 unique),
  type, entity_id, payload,
  created_at, author_id, device_id,
  status: à_envoyer | envoyé | acquitté | erreur,
  attempts, last_error
}
```

Règles :
1. Événements mis en **file d'attente locale**, renvoyés automatiquement en cas d'échec (backoff).
2. Le serveur **détecte les doublons** par `UUID` et applique les événements de façon **idempotente** :
   rejouer le même événement **ne crée rien de nouveau**.
3. Le tableau de bord affiche **dernière sync** + **nombre d'opérations en attente / en erreur**.
4. **Conflits** : enregistrés et résolus selon des règles explicites ; **aucune donnée financière
   écrasée silencieusement** (le conflit remonte à un validateur).

### 4.1 Règles d'autorité (proposition)
- Écritures **métier sensibles** (vente, caisse, réception, dépense) : **autorisées uniquement sur le LAN**
  au lancement. Le distant est **lecture** pour ces entités.
- **Paramètres sensibles** (prix, taux, rôles) : modifiables sur le serveur local, répliqués ensuite.

### 4.2 Limite reconnue
En cas de coupure, si un smartphone autonome et le serveur modifient le **même stock**, leurs états
peuvent **diverger temporairement**. La cohérence temps réel n'est **pas garantie hors réseau** — c'est
pourquoi la saisie de vente est **réservée au LAN**. Cette limite sera **documentée et expliquée** aux
utilisateurs.

---

## 5. Sécurité et audit

| Exigence | Mise en œuvre |
|---|---|
| Transport distant | **HTTPS/TLS** obligatoire |
| Mots de passe | **Hachage argon2/bcrypt**, jamais en clair, politique + limitation des tentatives |
| Accès | **RBAC** par permission, **vérifié à chaque action côté serveur (y compris API)** |
| Sessions | expiration, verrouillage auto (surtout caisse), révocation d'appareil retiré |
| Actions sensibles | **réauthentification** (mot de passe ou code personnel) |
| Attaques | protection CSRF, validation serveur, requêtes paramétrées (anti-injection), uploads contrôlés |
| Secrets | clés/taux/SMTP stockés **côté serveur**, hors du code et hors des appareils |
| **Audit** | journal **non modifiable** : action, objet, utilisateur, date/heure, appareil, **avant/après**, motif, statut, approbateur |

Le journal d'audit est **séparé** des journaux métier et **inaccessible en écriture** aux vendeurs.

---

## 6. Sauvegardes et reprise

- **Sauvegarde locale quotidienne** minimum (+ fréquente pour les données transactionnelles si besoin).
- **Sauvegarde distante chiffrée** dès que la connexion le permet.
- **Historique de versions** + rétention configurable ; protection contre la suppression (copies distantes).
- **Contrôle d'intégrité** automatique + **alerte** en cas d'échec (visible jusqu'à résolution).
- **Tests de restauration réguliers** dans un environnement de test (jamais sur la prod).
- La copie de sauvegarde n'inclut **jamais** les secrets en clair.

| Mesure | Proposition initiale |
|---|---|
| **RPO** (perte max acceptée) | **< 1 h** pour les ventes (à confirmer) |
| **RTO** (délai de reprise) | **< 4 h** (selon matériel, à confirmer) |
| **Rétention** | 30 jours en ligne + 12 mois archivés (à confirmer) |
| **Test de restauration** | mensuel + après tout changement majeur |

---

## 7. Matériel et déploiement

| Élément | Recommandation |
|---|---|
| PC serveur local | Windows 10/11, **8 Go RAM**, **SSD 256 Go+**, **onduleur** |
| Réseau | Box/routeur Wi-Fi dédié boutique + éventuel commutateur |
| Caisse | PC ou tablette + **imprimante thermique 80 mm** |
| Rapports | Imprimante A4 (optionnelle) |
| Distant | **VPS** (2 vCPU / 4 Go) + domaine + certificat TLS + SMTP |

**Mise en production** : environnement de test → **pilote** → migration des données initiales
(prix, quantités, soldes) **vérifiées physiquement et signées** par le propriétaire.

---

## 8. Observabilité

- Journaux d'erreur applicatifs.
- État de **synchronisation** (en attente / erreurs).
- État des **sauvegardes** (dernier succès / échec).
- **Centre de notifications** interne (alertes hiérarchisées et dédupliquées).
- Alertes critiques visibles **jusqu'à acquittement**.
