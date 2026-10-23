# BoutiqueGest — 01 · Cadrage fonctionnel

> Phase 1 — Cadrage final. Ce document fige les décisions, le périmètre et les règles de gestion
> **avant** toute programmation métier. Les points marqués « À confirmer » doivent être validés
> par le propriétaire de la boutique.

---

## 1. Décisions validées

| Sujet | Décision |
|---|---|
| Projet | **Nouveau projet depuis zéro** (pas une évolution de Tumika) |
| Technologie | **Python + Flask + SQLAlchemy + SQLite** (local), PostgreSQL possible plus tard à distance |
| Méthode | **Cadrage + maquettes d'abord**, puis développement par phases |
| Réseau | **Serveur local prioritaire** ; la boutique fonctionne sans Internet ; **synchronisation distante** ensuite |
| Langue | Français |
| Devises | **CDF et USD, soldes et caisses séparés** (jamais mélangés dans un même solde) |
| Sites | 1 boutique au lancement, architecture extensible |

---

## 2. Périmètre

### 2.1 Inclus
- Comptes, rôles et permissions.
- Catalogue produits, catégories, unités, conversions, prix.
- Ventes, reçus, retours, annulations contrôlées.
- Achats, fournisseurs, réceptions + validations.
- Stocks, inventaires, pertes, péremptions, valorisation.
- Caisses, modes de paiement, dépenses, clôtures.
- Crédits clients, dettes fournisseurs, échéances.
- Indicateurs de gestion (CA, coût, marge, trésorerie, stock).
- Rapports, exports Excel/PDF, alertes, e-mails.
- Journal d'audit, sauvegardes, synchronisation.

### 2.2 Hors périmètre initial
- Déclarations fiscales automatisées / plan comptable légal.
- Paie et gestion du personnel.
- Boutique publique en ligne, livraison, portail client.
- Intégrations Mobile Money/bancaires directes (sans étude d'API).
- IA avancée nécessitant un service payant.
- Multi-entrepôts / multi-boutiques avancé.

---

## 3. Rôles et permissions

Rôles prévus : **Propriétaire (super admin)**, **Vendeur**, **Responsable de stock** _(option)_,
**Comptable** _(option)_, **Auditeur** _(option)_, **Admin technique** _(option)_.

Actions granulaires : `consulter`, `creer`, `modifier_avant_validation`, `soumettre`, `valider`,
`annuler`, `exporter`, `administrer`.

| Permission | Propriétaire | Vendeur | Resp. stock | Comptable | Auditeur | Admin tech. |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| consulter produits/stock | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| créer une vente | ✅ | ✅ | — | — | — | — |
| voir ses propres ventes | ✅ | ✅ | — | ✅ | ✅ | — |
| préparer une réception | ✅ | — | ✅ | — | — | — |
| valider une réception | ✅ | — | _délégation_ | — | — | — |
| ouvrir/clôturer une caisse | ✅ | ✅ (la sienne) | — | — | — | — |
| valider une clôture | ✅ | — | — | _délégation_ | — | — |
| saisir une dépense | ✅ | — | ✅ | ✅ | — | — |
| valider une dépense | ✅ | — | — | _délégation_ | — | — |
| inventaire + pertes | ✅ | — | ✅ | — | — | — |
| rapports / exports | ✅ | limité | limité | ✅ | ✅ (lecture) | — |
| administrer (users, prix, param.) | ✅ | — | — | — | — | maint. |
| audit (lecture seule) | ✅ | — | — | — | ✅ | — |

**Contrôles** : aucune suppression définitive par un vendeur ; pas d'auto-validation de la caisse ;
réauthentification pour actions sensibles ; **toutes les vérifications refaites côté serveur**.

---

## 4. Décisions métier à figer (proposition par défaut)

> Le cahier des charges liste ces points comme **à valider**. Tant qu'ils ne sont pas confirmés,
> le développement démarre sur ces valeurs par défaut.

| # | Décision | Proposition par défaut |
|---|---|---|
| 1 | Nombre de boutiques | **1** au lancement (modèle multi-boutique extensible) |
| 2 | Vendeurs / caisses / appareils simultanés | **2–4 vendeurs**, **1–2 caisses**, **≤ 10 appareils** LAN |
| 3 | PC serveur local | **Windows 10/11**, 8 Go RAM, SSD, **onduleur recommandé** |
| 4 | Appareils distants hors LAN | **Consultation seule** au lancement ; saisie de vente réservée au LAN |
| 5 | Super admin / validateurs | Propriétaire = super admin ; validation déléguée à un gérant |
| 6 | Ventes à crédit | **Autorisées**, avec **plafond par client** et validation gérant |
| 7 | Moyens de paiement | Espèces CDF, espèces USD, **Mobile Money (référence)**, mixte, crédit |
| 8 | Devise de référence des rapports | **CDF**, avec **vue USD** et taux affiché |
| 9 | Taux de change | **Saisi manuellement** (1×/jour), **historique conservé**, jamais recalculé en silence |
| 10 | Valorisation du stock | **Coût moyen pondéré (CMP)** au lancement ; FIFO prévu en option |
| 11 | E-mails de rapports | **Rapport journalier** au propriétaire après clôture validée |
| 12 | Périphériques | **Imprimante thermique 80 mm** (reçus) + **A4** (rapports) ; scanner non requis |
| 13 | Budget hébergement | VPS distant + service SMTP (ligne mensuelle — montant à définir) |
| 14 | Obligations fiscales | **Hors logiciel** ; le système fournit exports et données de base |

---

## 5. Règles de gestion non négociables

1. **Immuabilité** : une opération validée n'est jamais effacée ni modifiée. Toute correction passe
   par une **contre-écriture / annulation / ajustement tracé** lié à l'original.
2. **Autorisations côté serveur** : jamais seulement dans l'interface.
3. **Monnaie** : montants en **Decimal** (précision contrôlée), **jamais** en flottant non contrôlé ;
   règles d'arrondi documentées (arrondi commercial, 2 décimales USD, entiers CDF).
4. **Identifiant unique + horodatage** sur chaque opération.
5. **Idempotence** : rejouer une synchronisation ne crée **jamais** de double vente ou de double mouvement.
6. **États distincts** : brouillon / en attente / validé / annulé / remboursé / synchronisé / erreur.
   Les données non validées sont **clairement séparées** des validées.
7. **Devises séparées** : chaque opération garde **montant d'origine + devise + taux appliqué + date**.
8. **Stock par mouvements** : aucun champ ne remplace une quantité sans **mouvement justificatif**.

---

## 6. Statuts et cycle de vie

| Document | Cycle de statuts |
|---|---|
| Vente | `brouillon → soumise → validée` · `annulée` · `remboursée (totale/partielle)` |
| Réception | `saisie → en attente → validée` (crée les mouvements de stock) |
| Dépense | `saisie → en attente → validée / rejetée` |
| Clôture de caisse | `ouverte → soumise → validée` (verrouillée) |
| Crédit client | `actif → partiellement réglé → soldé` · `en retard` |
| Événement de sync | `à envoyer → envoyé → acquitté / erreur (retries)` |

---

## 7. Critères d'acceptation (repris du CDC §19)

| ID | Test | Résultat attendu |
|---|---|---|
| T01 | Vendre plusieurs articles | Total correct, vente unique, stock décrémenté une fois |
| T02 | Vendre du lait au verre | Conversion exacte selon le volume configuré |
| T03 | Réception non validée | Stock officiel inchangé (statut provisoire exclu) |
| T04 | Valider une réception | Mouvement unique + validateur + horodatage |
| T05 | Clôture avec écart | Écart calculé, explication demandée, aucune vente modifiée |
| T06 | Annuler une vente validée | Trace de l'annulation, stock/caisse cohérents |
| T07 | Paiement CDF + USD | Soldes et rapports séparés, conversion explicite |
| T08 | Coupure Internet | Ops locales continuent, file de sync conservée |
| T09 | Rétablir Internet | Aucun doublon, sync + erreurs consultables |
| T10 | Échec de sauvegarde | Alerte émise, visible jusqu'à résolution |
| T11 | Restaurer une sauvegarde | Données restaurées, cohérence vérifiée (env. de test) |
| T12 | Utilisateur non autorisé | Refus côté serveur + événement journalisé |
| T13 | Export Excel | Totaux identiques à l'écran (mêmes filtres/statuts) |
| T14 | Rapport journalier | Généré après clôture, envoyé ou mis en attente |
| T15 | Inventaire avec perte | Écart, motif, approbation, effet de stock traçables |
| T16 | Échéance de crédit | Alerte déclenchée selon date et configuration |
