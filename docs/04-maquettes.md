# BoutiqueGest — 04 · Maquettes d'écrans

> Wireframes des écrans principaux (PC en priorité, puis tablette/smartphone). Objectif : valider
> l'ergonomie **avant** le développement. Une version HTML cliquable pourra être produite ensuite.

---

## 1. Principes d'interface

| Élément | Choix |
|---|---|
| Direction | Moderne, sobre, **premium et légère** |
| Palette | **Bleu profond** (#1e3a8a) · blanc · **gris clair** ; couleurs d'état limitées (vert/ambre/rouge) |
| Typographie | 1 police lisible, hiérarchie claire, espaces réguliers |
| PC | Tableaux denses mais lisibles + graphiques utiles |
| Mobile | **Cartes synthétiques** au lieu de tableaux |
| Caisse (POS) | **Gros boutons**, recherche rapide, **étapes minimales** |
| Feedback | Messages d'erreur **explicatifs**, guides courts pour non-spécialistes |
| États | Badges visibles : brouillon · en attente · validé · rejeté · synchronisé · erreur |

**Accessibilité** : zones tactiles larges, contrastes lisibles, **jamais la couleur seule**,
navigation clavier, filtres rapides et effaçables, confirmation des actions sensibles.

---

## 2. Connexion

```
┌──────────────────────────────────────────────┐
│                  BoutiqueGest                  │
│                                              │
│   Utilisateur : [_____________________]       │
│   Mot de passe: [_____________________]       │
│                                              │
│        [ Se connecter ]                       │
│                                              │
│   État : ● Serveur local · ○ Distant         │
└──────────────────────────────────────────────┘
```

---

## 3. Tableau de bord

```
┌───────────────────────────── Barre supérieure ─────────────────────────────┐
│ ☰  BoutiqueGest      🔍 Rechercher      ● Local  ⟳ Sync  ⚠ Alertes  👤 Joe  │
├──────────────┬──────────────────────────────────────────────────────────────┤
│ NAV          │  Ventes        Marge       Caisse        Stock     Crédits   │
│ ▸ Tableau    │ ┌────────┐ ┌────────┐ ┌────────────┐ ┌────────┐ ┌──────────┐  │
│ ▸ Caisse(POS)│ │ 320 000│ │ 18,4 % │ │ 210 000 CDF│ │ 47 art.│ │ 60 000   │  │
│ ▸ Produits   │ │ CDF    │ │        │ │   +40 USD  │ │ 3 bas  │ │ CDF      │  │
│ ▸ Achats     │ └────────┘ └────────┘ └────────────┘ └────────┘ └──────────┘  │
│ ▸ Stock      │                                                              │
│ ▸ Dépenses   │  ⚠ À valider (3)           📈 Ventes 7 jours   🥧 Répartition │
│ ▸ Crédits    │   • Réception #104          ┌──────────────┐    ┌──────────┐  │
│ ▸ Rapports   │   • Clôture caisse #22      │   ╱╲    ╱╲   │    │  ● Boisson│ │
│ ▸ Admin      │   • Dépense #57             │  ╱  ╲__╱  ╲  │    │  ● Eau    │ │
│              │                             └──────────────┘    │  ● Lait   │ │
│              │  Dernière sync : 12:41 ✓    En attente : 0       └──────────┘  │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

---

## 4. Point de vente (caisse)

```
┌──────────── Panier (gauche) ────────────┬──────── Produits (droite) ─────────┐
│ Recherche produit : [_______________🔍] │ Catégories : [Tout][Boisson][Eau]  │
│                                         │                                    │
│ Eau bidon  x2     5 000    [−] [+]  🗑  │ ┌────────┐ ┌────────┐ ┌────────┐   │
│ Lait (L)   0,6 L  3 000    [−] [+]  🗑  │ │ Eau    │ │ Lait   │ │ Coca   │   │
│                                         │ │ bidon  │ │ 1 L    │ │ 33 cl  │   │
│                                         │ │ 2 500  │ │ 5 000  │ │ 1 500  │   │
│ ─────────────────────────────────────── │ └────────┘ └────────┘ └────────┘   │
│ Total              8 000 CDF            │ ┌────────┐ ┌────────┐              │
│ Remise [____] Devise (•CDF ○USD)        │ │ Verre  │ │ Sucre  │              │
│ Paiement : (•Espèces)(○Mobile)(○Crédit) │ │ 200 mL │ │ 1 kg   │              │
│ Reçu [ 10 000 ] Monnaie : 2 000 CDF     │ └────────┘ └────────┘              │
│                                         │                                    │
│ [      VALIDER LA VENTE  ✅      ]      │                                    │
└─────────────────────────────────────────┴────────────────────────────────────┘
```

---

## 5. Produits

```
┌ Produits ──────────────────────────────────────────────── [ + Nouveau produit ]
├──────────────────────────────────────────────────────────────────────────────┤
│ Code    Nom            Catégorie  Stock   Unité   Prix vente  Seuil  Statut   │
│ LAT-1L  Lait 1 L       Lait       9,4 L   L       5 000 CDF   2 L    ● Actif  │
│ EAU-BD  Eau bidon      Eau        38      bidon   2 500 CDF   10     ● Actif  │
│ COCA33  Boisson 33 cl  Boisson    120     bouteil 1 500 CDF   24     ● Actif  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Fiche « Lait 1 L » : unités de vente [L · verre=0,2 L], lots, historique prix │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Achats / Réception

```
┌ Réception #104 — Fournisseur « Alpha » ─────────── statut : ⧗ EN ATTENTE ─────┐
├──────────────────────────────────────────────────────────────────────────────┤
│ Produit        Qté attendue  Qté reçue  Acceptée   Manquant  Dommage  Coût    │
│ Eau bidon           50           48        48         2        —     2 200   │
│ Coca 33 cl         120          120       118         —        2     1 200   │
├──────────────────────────────────────────────────────────────────────────────┤
│ Motif (si écart) : [________________________________________]               │
│                                           [ Valider la réception ✅ ]          │
└──────────────────────────────────────────────────────────────────────────────┘
```

> Validation → **mouvements de stock définitifs** + validateur + horodatage. Avant validation,
> le stock officiel est **inchangé**.

---

## 7. Stock / Inventaire

```
┌ Stock ──────────────────────── [ + Inventaire ] [ + Perte ] [ Export ] ───────┐
│ Filtre catégorie [Tout ▾]  ● Stock bas (3)  ● Rupture (1)  ● Péremption (2)   │
├──────────────────────────────────────────────────────────────────────────────┤
│ Produit        Quantité  Valorisation  Dernier mvt  Lot / péremption   État    │
│ Lait 1 L        9,4 L    28 200 CDF    2 h         LAT-01 · 12/11      ✔      │
│ Eau bidon       38       83 600 CDF    10 h        —                   ⚠ bas  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Inventaire #7 : Théorique 38 · Compté 36 · Écart −2 (−4 400 CDF) │  Motif [ ] │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Caisse / Clôture

```
┌ Caisse — Session #22 (Vendeur : Joe) ───────────────● OUVERTE  [ Clôturer ] ──┐
├──────────────────────────────────────────────────────────────────────────────┤
│ Devise : (•CDF  ○USD)   Solde initial : 50 000 CDF                            │
│                                                                              │
│ Solde théorique = 50 000 + 180 000 − 20 000 = 210 000 CDF                     │
│ Montant compté  : [_________]    Écart : −5 000 CDF                            │
│ Explication de l'écart : [_______________________________________]           │
│                                                                              │
│ Mouvements : ventes 12 · remboursements 0 · retraits 1 · dépenses 2           │
│                                        [ Soumettre la clôture ]               │
└──────────────────────────────────────────────────────────────────────────────┘
```

> L'écart **ne modifie jamais** les ventes ; il est expliqué, puis validé par une personne habilitée.

---

## 9. Dépenses

```
┌ Dépenses ───────────────────────────────────────────── [ + Nouvelle dépense ] ┐
│ Date       Catégorie   Motif           Montant    Devise  Justif.  Statut      │
│ 18/10      Loyer       Loyer trimestre 120 000    CDF     📎       ✔ validée   │
│ 18/10      Transport   Livraison eau    10 000    CDF     📎       ⧗ attente   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Crédits / Fournisseurs

```
┌ Crédits ───────────────────────── [ Clients ] [ Fournisseurs ] [ Échéances ] ─┐
│ Client      Montant    Réglé     Reste     Devise  Échéance    État           │
│ Kabila      20 000     5 000     15 000    CDF     25/10       ⧗ proche       │
│ Maman N.    50 000     50 000    0         CDF     10/10       ✔ soldé        │
├──────────────────────────────────────────────────────────────────────────────┤
│ ⚠ 2 crédits en retard · [ + Règlement ]                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Rapports

```
┌ Rapports ─── Période : (•Jour ○Semaine ○Mois ○Trim. ○Année ○Libre) ─ [Excel] ─┐
├──────────────────────────────────────────────────────────────────────────────┤
│ CA net      Coût marchandises  Marge brute   Charges    Résultat estimé        │
│ 320 000 CDF 210 000 CDF        110 000 CDF   35 000     75 000 CDF             │
│ 40 USD                             (vue USD au taux 2 800, source : manuel)    │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Ventes][Achats][Stocks][Caisse][Dépenses][Crédits][Résultat][Audit]           │
│ Détail : cliquez un total → liste des opérations qui le composent              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Administration

```
┌ Administration ── [Utilisateurs][Rôles][Paramètres][Devises][Backups][Sync][Audit]
├──────────────────────────────────────────────────────────────────────────────┤
│ Utilisateur  Rôle           Actif   Dernière connexion   Sessions             │
│ Joe          Vendeur        ●       12:40                1 (tablette)         │
│ Sarah        Resp. stock    ●       11:05                1                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ Sauvegarde : ✔ 03:00 (locale) · ✔ 03:20 (distante)   Intégrité : OK           │
│ Synchronisation : dernier envoi 12:41 · en attente 0 · erreurs 0              │
│ Journal d'audit : [ rechercher une action / un utilisateur / une date ]       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. Responsive (tablette / smartphone)

- **Navigation** : menu replié (☰), barre d'actions contextuelle en bas.
- **Tableaux** → **cartes** (1 enregistrement = 1 carte avec les champs clés + actions).
- **POS** : produit en grille 2 colonnes ; panier accessible par onglet ; bouton **Valider** fixe.
- **Caisse** : clavier numérique large pour les montants reçus et le comptage.
- Les états (en attente / validé / erreur) restent **toujours visibles**, texte + couleur.
