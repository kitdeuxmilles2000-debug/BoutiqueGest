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
| [`docs/05-synchronisation-render.md`](docs/05-synchronisation-render.md) | Configuration du transfert sécurisé local vers Render |

---

## Principes non négociables

1. Aucune opération validée n'est effacée/modifiée → **correction par contre-écriture tracée**.
2. Autorisations **vérifiées côté serveur** (y compris API).
3. Montants en **Decimal**, devises **jamais mélangées**.
4. **Idempotence** de la synchronisation (aucun doublon).
5. Tout changement de stock provient d'un **mouvement justificatif**.
6. Sauvegardes **testées** (RPO/RTO à confirmer).

## Formats de vente et conversions

Dans la fiche produit ou lors de la création depuis une entrée de stock, choisissez le
type du produit : quatre lignes de formats facultatifs sont proposées, et il est possible
d'en ajouter davantage. Les unités de stock des nouveaux produits sont automatiquement
la plus petite unité : ml pour les liquides, pièce pour les cartons, g pour le poids et
cm pour les tissus. Chaque format peut avoir son propre prix.

Exemples :

- Eau en ml : **Bidon 5 L** consomme `5000 ml`; **Bidon 10 L** consomme `10000 ml`.
- Lait en ml : un **Verre 25 ml** consomme `25 ml` (la capacité d'un verre est limitée
  à 1000 ml); chaque format a son prix.
- Carton compté en pièces : **Pièce** consomme une pièce et **Carton 12 pièces** en
  consomme douze.
- Poids en g : **Kilogramme** consomme `1000 g`; un sac de 25 kg consomme `25000 g`.
- Tissu en cm : **Mètre** consomme `100 cm`; un rouleau de 10 m consomme `1000 cm`.

Chaque format configuré apparaît comme un choix distinct au POS. La vente, le calcul du
coût et la mise à jour du stock utilisent le même facteur de conversion. Les contenus
invalides et les verres de plus de 1000 ml sont rejetés avant l'enregistrement.
À la création rapide depuis une entrée de stock, choisissez aussi l'unité de réception :
par exemple **3 bidons de 20 L** créent une entrée de `60000 ml`. Le formulaire propose
la même sélection pour un produit existant. Pour un produit existant, le prix d'achat
se saisit directement par unité de réception choisie (pièce, carton, bidon, etc.) ; le
formulaire calcule la valeur de l'entrée et le coût moyen estimé après réception. Pour
un nouveau produit, le prix est saisi par unité de stock et converti selon le format reçu.
Le coût moyen pondéré du stock n'est recalculé qu'après validation de la réception.
L'écran Stock affiche la valeur au coût moyen et une marge brute potentielle estimée,
séparément en CDF et en USD, au prix du format de vente par défaut. Cette estimation
n'est pas un bénéfice réalisé et n'inclut pas les charges. Les marges réellement
enregistrées sur les ventes et leur pourcentage du chiffre d'affaires figurent dans
Rapports, par période et par devise. Les coûts unitaires moyens sont conservés avec
une précision suffisante pour les conditionnements fractionnaires (par exemple
100 000 CDF / 12 pièces); les montants affichés restent arrondis au centime.
Rapports affiche également le total des achats réceptionnés pendant la période choisie,
séparé par devise; ce total est aussi inclus dans le rapport envoyé par e-mail et l'export
CSV. Les achats sont comptés à leur date de réception. Ils ne sont pas soustraits une
seconde fois du résultat, car leur coût est déjà pris en compte au moment des ventes.
L'envoi se configure dans Administration > E-mails (serveur SMTP et destinataire); un
rapport peut être envoyé manuellement ou automatiquement à la clôture de caisse.

Les nouveaux produits sont protégés contre les noms identiques après normalisation
(majuscules/minuscules et espaces) dans une même catégorie. Les données historiques
ne sont pas supprimées. Une quantité initiale peut être saisie sur la fiche produit,
en unité de base ou dans un format configuré ; elle crée une entrée en attente de
validation. Une entrée de stock identique le même jour (produit, quantité de base,
coût de base et lot) déclenche une alerte. Pour confirmer qu'il s'agit d'un nouvel
approvisionnement, un mot de passe administrateur est requis et l'autorisation est
conservée dans le journal d'audit.

## Caisse et point de vente

Quand aucun tiroir n'est ouvert, le point de vente affiche directement le choix d'une
caisse active (CDF ou USD) et le fond de départ ; le bouton ouvre la caisse puis ramène
au catalogue. Les caisses par défaut sont initialisées si elles n'existent pas encore.
Le catalogue POS respecte la devise du tiroir et n'affiche que les produits actifs,
dotés d'un prix dans cette devise et d'un stock validé.

Les contrôles de vente sont recalculés côté serveur : stock cumulé des lignes d'un même
produit, unités de vente disponibles, remise non négative et inférieure au sous-total,
paiements valides ne dépassant pas le total, devise correspondante au tiroir. Les montants
sont arrondis au centime ; le stock et le solde de caisse ne changent que dans la
transaction de vente validée.
Appliquez la migration de base de données avant de relancer l'application :
`python -m flask --app run db upgrade`.
Le raccourci Windows lance également cette commande au démarrage et bloque le lancement
du serveur si une migration échoue.

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
- [x] **Phase 8 — Local / distant** (sauvegardes vérifiées/restaurables, transfert authentifié local → Render).
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
| Synchronisation locale → Render | ✅ | Instantané gzip/HTTPS, fusion par UUID, rendu cloud en lecture seule |
| Stock par mouvements justificatifs | ✅ | Tout changement via `StockMovement`, CMP recalculé (T01/T04/T15) |
| Sauvegardes testées / restauration | ✅ | `sqlite backup` + `integrity_check` + restauration vérifiée (T10/T11) |
| Audit non modifiable | ✅ | Journal append-only (action, objet, user, avant/après, IP) |
| Devises & taux | ✅ | Opérations mono-devise ; aucune conversion silencieuse ; **taux manuel historisé** (décision 9) |
| Crédits clients / dettes fournisseurs | ✅ | Plafond client, échéances, statuts auto, alertes (T16) |
| E-mails / rapport journalier | ✅ | File d'attente `OutboxMessage` ; envoi SMTP si configuré, sinon « en attente » (décision 11) |
| Responsivité (PC/tablette/mobile) | ✅ | Google viewport, sidebar + hamburger, tableaux défilants, grilles fluides, media queries 860/520 px |

> Confidentialité : document de travail du projet. Ne pas diffuser hors du cercle du projet.
