# BoutiqueGest

Système intégré de **gestion commerciale, de stock, de caisse et de finances** pour une boutique
mixte (boissons, eau, lait vendu au litre/verre, accessoires et autres articles de détail).

- **Multiplateforme** (PC, tablette, smartphone) · **local + en ligne**
- **CDF et USD**, soldes séparés
- Fiabilité des chiffres · traçabilité · validation physique · continuité hors ligne

> Statut : **Tous les modules opérationnels et la recette finale validée (30/30 vérifications, critères
> T01–T16 du CDC + responsivité).** Reste le pilote en boutique et la mise en production.

---

## Décisions déjà validées

| Sujet | Choix |
|---|---|
| Base | **Nouveau projet depuis zéro** |
| Stack | **Python + Flask + SQLAlchemy + SQLite** |
| Méthode | **Cadrage + maquettes d'abord**, développement par phases |
| Réseau | **Serveur local prioritaire** + synchronisation distante idempotente |

---

## Documents (à lire dans l'ordre)

| Fichier | Contenu |
|---|---|
| [`docs/01-cadrage.md`](docs/01-cadrage.md) | Périmètre, rôles/permissions, règles de gestion, décisions métier, critères d'acceptation |
| [`docs/02-architecture.md`](docs/02-architecture.md) | Architecture local/distant, synchronisation, sécurité, audit, sauvegardes, matériel |
| [`docs/03-modele-donnees.md`](docs/03-modele-donnees.md) | Entités, champs, relations, contraintes d'intégrité |
| [`docs/04-maquettes.md`](docs/04-maquettes.md) | Wireframes des écrans + principes UI premium |

---

## Principes non négociables

1. Aucune opération validée n'est effacée/modifiée → **correction par contre-écriture tracée**.
2. Autorisations **vérifiées côté serveur** (y compris API).
3. Montants en **Decimal**, devises **jamais mélangées**.
4. **Idempotence** de la synchronisation (aucun doublon).
5. Tout changement de stock provient d'un **mouvement justificatif**.
6. Sauvegardes **testées** (RPO/RTO à confirmer).

---

## Organisation du code

```
app/
  __init__.py        Application factory
  config.py          Configuration
  extensions.py      db, migrate, login, csrf
  cli.py             commandes : init-db, seed, reset-db
  models/            BaseModel, User, Role, Permission, catalogue, stock, ventes, caisse, finance
  security/          permissions, decorateurs (permission_required), audit, session
  services/          auth, seed, stock, sales, cash, finance, reports, purchases, backup, sync
  routes/            auth, main, admin, products, purchases, stock, cash, sales, pos, partners, expenses, credits, reports
  templates/         base, auth/, dashboard, admin/, products/, purchases/, stock/, cash/, sales/, pos/, partners/, expenses/, credits/, reports/, errors/
  static/css/        app.css  (aucune dependance externe)
migrations/          migrations Alembic versionnees
docs/                cadrage, architecture, modele de donnees, maquettes
run.py               point d'entree : python run.py
```

## Démarrage (développement)

```powershell
# 1. Environnement virtuel
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configuration (facultatif)
Copy-Item .env.example .env   # puis adapter les valeurs

# 3. Base de donnees + donnees de reference
python -m flask --app run db upgrade
python -m flask --app run seed        # cree admin / admin123 (mot de passe a changer)

# 4. Lancer
python run.py        # http://localhost:5000
```

> Au premier demarrage, seul un compte **admin** existe. Il doit **changer son mot de passe**,
> puis créer les comptes vendeurs (Administration → Utilisateurs).

## Plan de réalisation (phases)

1. **Cadrage final** — décisions validées, questions métier tranchées. _(fait)_
2. **Conception** — architecture, modèle de données, maquettes. _(fait)_
3. **Socle technique** — auth, rôles/permissions, audit, migrations. _(fait)_
4. **Produits & stock** — catalogue, conversions, mouvements, inventaires. _(fait)_
5. **Ventes & caisse** — POS, paiements, clôtures, rapprochements. _(fait)_
6. **Dépenses & dettes** — dépenses, crédits, échéances, règlements. _(fait)_
7. **Rapports** — tableaux de bord, exports Excel/PDF. _(fait)_
8. **Local / distant** — sauvegardes vérifiées, restauration, synchronisation idempotente. _(fait)_
9. **Achats / réceptions** — commandes fournisseurs, réception, dette fournisseur. _(fait)_
10. **Paramétrage** — taux de change manuel historisé, e-mails/rapport journalier. _(fait)_
11. **Recette** — parcours de bout en bout, critères du CDC. _(fait : 30/30 + 12/12 phase 10)_
12. **Pilote & mise en production** — tests utilisateurs, formation, migration des données initiales.

> **Décision phase 5** : une vente est **mono-devise** (CDF *ou* USD). Chaque caisse porte une
> devise ; une vente hérite de la devise de la caisse ouverte. Les devises ne sont jamais mélangées.

---

## Prochaines étapes

- [ ] Valider les **14 décisions métier** (voir `docs/01-cadrage.md` §4).
- [ ] Valider les **maquettes** (`docs/04-maquettes.md`).
- [ ] Confirmer le **matériel** et le **budget** d'hébergement/e-mails.
- [x] Socle technique (auth, rôles/permissions, audit, migrations).
- [x] **Phase 4 — Produits & stock** (catalogue, unités/conversions, entrées/pertes, inventaires).
- [x] **Phase 5 — Ventes & caisse** (POS, paiements, clôtures/validation, annulation, remboursement).
- [x] **Phase 6 — Dépenses & dettes** (partenaires, dépenses validées, crédits/échéances, règlements).
- [x] **Phase 7 — Rapports** (indicateurs par devise, trésorerie, top produits, export CSV/imprimable).
- [x] **Phase 8 — Local / distant** (sauvegardes vérifiées/restaurables, sync idempotente, file d'attente).
- [x] **Phase 9 — Achats / réceptions** (commandes fournisseurs, réception stock/CMP, dette fournisseur, contre-écriture).
- [x] **Phase 10 — Paramétrage** (taux de change manuel historisé, file d'e-mails, rapport journalier).
- [x] **Recette finale** — critères T01–T16 du CDC validés + responsivité (30/30 vérifications).
- [ ] **Pilote** : tests utilisateurs, formation, migration des données initiales signées par le propriétaire.

### Conformité au cahier des charges

| Exigence | État | Mise en œuvre |
|---|---|---|
| Immuabilité des opérations validées | ✅ | Contre-écriture tracée (annulation/remboursement/retour), audit horodaté |
| Autorisations côté serveur | ✅ | `permission_required` sur chaque route ; refus 403 journalisé (T12) |
| Montants en Decimal, devises séparées | ✅ | `Numeric`/`Decimal`, ventes et caisses mono-devise CDF/USD |
| Idempotence de synchronisation | ✅ | `SyncEvent.idempotency_key` unique, rejeu sans doublon (T09) |
| Stock par mouvements justificatifs | ✅ | Tout changement via `StockMovement`, CMP recalculé (T01/T04/T15) |
| Sauvegardes testées / restauration | ✅ | `sqlite backup` + `integrity_check` + restauration vérifiée (T10/T11) |
| Audit non modifiable | ✅ | Journal append-only (action, objet, user, avant/après, IP) |
| Devises & taux | ✅ | Opérations mono-devise ; aucune conversion silencieuse ; **taux manuel historisé** (décision 9) |
| Crédits clients / dettes fournisseurs | ✅ | Plafond client, échéances, statuts auto, alertes (T16) |
| E-mails / rapport journalier | ✅ | File d'attente `OutboxMessage` ; envoi SMTP si configuré, sinon « en attente » (décision 11) |
| Responsivité (PC/tablette/mobile) | ✅ | Google viewport, sidebar + hamburger, tableaux défilants, grilles fluides, media queries 860/520 px |

> Confidentialité : document de travail du projet. Ne pas diffuser hors du cercle du projet.
