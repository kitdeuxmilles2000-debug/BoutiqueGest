# BoutiqueGest — 03 · Modèle de données

> Modèle indicatif qui sera finalisé en conception technique. Chaque entité porte un **identifiant
> unique**, un **horodatage**, et, pour les documents validés, un **cycle de statut** et une
> **traçabilité d'audit**.

---

## 1. Conventions générales

| Règle | Choix |
|---|---|
| Clé primaire | `id` entier auto-incrémenté **+** `uuid` (UUIDv4) unique — clé de synchronisation |
| Montants | `Numeric(18,2)` en **Decimal** + colonne **`currency`** explicite (`CDF`/`USD`) — jamais implicite |
| Quantités | `Numeric(18,3)` (litres/millilitres), entier pour les pièces |
| Dates | stockées en **UTC**, affichées selon le fuseau configuré |
| Suppression | **interdite** sur les documents validés ; désactivation (`actif=false`) pour les référentiels |
| Traçabilité | `created_at`, `created_by` sur tout ; `validated_at`, `validated_by`, `motif` sur les validés |
| Change | toute conversion conserve **taux + date + source** appliqués |

---

## 2. Comptes, rôles et sécurité

| Entité | Champs clés |
|---|---|
| **User** | `nom`, `username`, `password_hash`, `pin_hash` (validations), `role_id`, `actif`, `last_login` |
| **Role** | `nom`, `description`, `est_super_admin` |
| **Permission** | `code` (`consulter`, `creer`, `valider`, `annuler`, `exporter`, `administrer`…) |
| **RolePermission** | `role_id`, `permission_id`, `autorise` |
| **UserSession** | `user_id`, `device_id`, `created_at`, `expires_at`, `revoked`, `ip` |
| **AuditLog** | `action`, `entity`, `entity_uuid`, `user_id`, `at`, `device_id`, `valeur_avant`, `valeur_apres`, `motif`, `approbateur_id` |

> `AuditLog` est en **append-only** (aucune modification/suppression applicative).

---

## 3. Catalogue : produits, unités, conversions

| Entité | Champs clés |
|---|---|
| **Category** | `nom`, `actif` |
| **Unit** | `code` (`L`, `mL`, `bidon`, `bouteille`, `verre`, `piece`, `casier`, `carton`), `type` (`volume`/`contenance`/`piece`) |
| **Product** | `code` (unique), `nom`, `category_id`, `unite_stock_id`, `seuil_alerte`, `actif`, `pereissable`, `suivi_lot` |
| **ProductUnitConversion** | `product_id`, `unit_id`, `facteur` (ex. 1 verre = 0.2 L), `est_vente_autorisee` |
| **PriceHistory** | `product_id`, `type` (`achat`/`vente`), `prix`, `currency`, `date_effet`, `auteur_id` |
| **Batch (Lot)** | `product_id`, `numero_lot`, `date_peremption`, `qte_disponible`, `cout_unitaire` |

**Exemples de conversion** (paramétrables, jamais imposés sans validation) :
`Eau bidon` : stock = bidon. · `Eau bouteille` : bouteille/carton. · `Lait` : stock en L,
vente au **verre = 0,2 L**. · `Boisson` : bouteille/casier/carton. · `Accessoire` : pièce.

---

## 4. Partenaires

| Entité | Champs clés |
|---|---|
| **Supplier** | `nom`, `contact`, `devise_usuelle`, `conditions`, `actif` |
| **Customer** | `nom`, `contact`, `plafond_credit`, `actif` |

---

## 5. Achats et réceptions

| Entité | Champs clés |
|---|---|
| **PurchaseOrder** | `numero`, `supplier_id`, `date`, `statut`, `currency` |
| **PurchaseOrderLine** | `po_id`, `product_id`, `qte`, `prix_unitaire`, `currency` |
| **Reception** | `numero`, `supplier_id`, `po_id` (option), `statut` (`en_attente`/`validee`), `valide_par`, `date` |
| **ReceptionLine** | `reception_id`, `product_id`, `qte_attendue`, `qte_recue`, `qte_acceptee`, `manquant`, `exces`, `dommage`, `cout_unitaire`, `currency` |

> La **rélévation seule** (statut `validee`) crée les **mouvements de stock définitifs**.
> Une réception en attente **ne modifie pas** le stock officiel.

---

## 6. Ventes

| Entité | Champs clés |
|---|---|
| **Sale** | `numero` (unique), `date`, `vendeur_id`, `cash_session_id`, `montant_total`, `currency`, `statut` (`brouillon`/`soumise`/`validee`/`annulee`/`remboursee`), `remise`, `sale_origine_id` (correction) |
| **SaleLine** | `sale_id`, `product_id`, `unit_id`, `qte`, `qte_base` (convertie), `prix_unitaire`, `remise_ligne`, `cout_unitaire_cmp`, `currency` |
| **Payment** | `sale_id` (ou crédit), `montant`, `currency`, `moyen` (`espece_cdf`/`espece_usd`/`mobile_money`/`banque`), `reference`, `date` |
| **Refund** | `sale_id`, `montant`, `currency`, `moyen`, `motif`, `remise_en_stock` (bool), `autorise_par` |

Statuts distincts : en cours / soumise / validée / annulée / remboursée.

---

## 7. Stock

| Entité | Champs clés |
|---|---|
| **StockMovement** | `product_id`, `type` (`reception`/`vente`/`retour`/`transfert`/`perte`/`correction_inventaire`), `qte` (+/−), `cout_unitaire`, `currency`, `source_type`, `source_uuid`, `auteur_id`, `date`, `batch_id` |
| **InventorySession** | `date`, `responsable_id`, `perimetre`, `statut` |
| **InventoryLine** | `session_id`, `product_id`, `qte_theorique`, `qte_comptee`, `ecart`, `ecart_valeur`, `motif`, `approuve_par` |

> **Tout** changement de stock vient d'un `StockMovement`. Aucun champ ne permet de **remplacer**
> une quantité sans mouvement. Sortie **FEFO** possible pour les périssables.

---

## 8. Caisses et clôtures

| Entité | Champs clés |
|---|---|
| **CashRegister** | `nom`, `devise` (CDF ou USD) |
| **CashSession** | `register_id`, `vendeur_id`, `ouverte_at`, `solde_initial`, `statut` (`ouverte`/`soumise`/`validee`), `solde_theorique`, `solde_compte`, `ecart`, `motif_ecart`, `valide_par` |
| **CashMovement** | `session_id`, `type` (`vente`/`remboursement`/`apport`/`retrait`/`depense`), `montant`, `currency`, `source_uuid`, `date` |

**Formule** : `solde_theorique = solde_initial + encaissements − décaissements`.
**Écart** (par devise) : `solde_compte − solde_theorique`. Un écart demande une **explication** ;
le système **ne modifie jamais** les ventes pour l'annuler.

---

## 9. Dépenses, crédits et dettes

| Entité | Champs clés |
|---|---|
| **Expense** | `date`, `montant`, `currency`, `category_id`, `motif`, `beneficiaire`, `moyen`, `justificatif_id`, `statut`, `cree_par`, `valide_par` |
| **Credit** | `type` (`client`/`fournisseur`), `partenaire_id`, `montant_initial`, `currency`, `solde_restant`, `date`, `statut` |
| **Installment (Échéance)** | `credit_id`, `date_echeance`, `montant_du`, `statut` (`a_venir`/`echue`/`payee`) |
| **Settlement (Règlement)** | `credit_id`, `montant`, `currency`, `moyen`, `date`, `reference` |

> Une vente à crédit **n'augmente pas la caisse** ; seule sa créance augmente. Le règlement
> ultérieur réduit la créance **et** augmente la trésorerie.

---

## 10. Devises et taux

| Entité | Champs clés |
|---|---|
| **Currency** | `code` (`CDF`/`USD`), `symbole`, `decimales` |
| **ExchangeRate** | `base`, `cible`, `taux`, `date_effet`, `source`, `auteur_id` |

> Les anciennes opérations **ne sont jamais recalculées** à un nouveau taux. Une vue convertie
> affiche **toujours** la devise de référence et le taux retenu.

---

## 11. Infrastructure : sync, sauvegardes, notifications

| Entité | Champs clés |
|---|---|
| **SyncEvent** | `uuid`, `type`, `entity_uuid`, `payload`, `device_id`, `status`, `attempts`, `last_error`, `created_at` |
| **BackupJob** | `started_at`, `finished_at`, `destination`, `statut`, `taille`, `erreur` |
| **EmailLog** | `rapport`, `destinataires`, `statut`, `tentatives`, `erreur`, `envoye_at` |
| **Notification** | `niveau`, `categorie`, `message`, `lue`, `acquittee`, `created_at` |

---

## 12. Relations principales (résumé)

```
Category 1─n Product 1─n ProductUnitConversion
Product 1─n StockMovement        Product 1─n Batch
Supplier 1─n PurchaseOrder 1─n PurchaseOrderLine
PurchaseOrder 1─n Reception 1─n ReceptionLine ─▶ StockMovement
Sale 1─n SaleLine 1─n (StockMovement)     Sale 1─n Payment / Refund
CashRegister 1─n CashSession 1─n CashMovement
Credit 1─n Installment        Credit 1─n Settlement
User 1─n AuditLog / SyncEvent / Session
Currency 1─n ExchangeRate
```

---

## 13. Contraintes d'intégrité (extraits)

- `Product.code`, `Sale.numero`, `Sale.uuid`, `SyncEvent.uuid` : **uniques**.
- Montant et devise obligatoires sur tout mouvement financier ; `currency ∈ {CDF, USD}`.
- `Sale` validée : `montant_total = Σ(SaleLine) − remises` (contrôle applicatif + test).
- `StockMovement` référence **toujours** une source (`source_uuid`).
- Pas de `DELETE` applicatif sur `AuditLog`, `StockMovement`, `Sale`/`SaleLine` validées.
- Réception `en_attente` : aucun `StockMovement` associé.
