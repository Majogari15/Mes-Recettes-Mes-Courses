# Mes Recettes, Mes Courses (application Windows) — v1

**⚠️ Correction par rapport à la livraison précédente** : la première
version que j'avais livrée avait été modifiée à partir d'un fichier
`main.py` périmé, portant encore l'ancien nom "Mon Livre de Recettes" —
alors que votre vraie version 1.2.2 s'appelle **"Mes Recettes, Mes
Courses"** (le même nom que l'application mobile). Cette archive corrige
le problème : mêmes modifications, mais appliquées sur votre vrai
fichier 1.2.2 (celui que vous m'avez transmis). Vérifié en détail :
aucune autre différence entre les deux fichiers de départ, uniquement
le nom de l'application — vous n'avez donc perdu aucune fonctionnalité
ni correction dans l'échange précédent.

Premier numéro de version formel pour cette application — aucun système
de version n'existait jusqu'ici (seulement un suivi par date de session).
Ce numéro marque le début d'un suivi formel, pas le tout début du
développement de l'application (déjà mature à ce stade).

## Nouveautés de cette version

- **Identifiant stable par recette**, avec migration automatique et
  silencieuse des recettes déjà existantes qui n'en avaient pas encore
  un — nécessaire pour la compatibilité avec l'application mobile.
- **Compatibilité des sauvegardes avec l'application mobile** ("Mes
  Recettes, Mes Courses" mobile) : deux nouveaux boutons dans la fenêtre
  Import/Export ("Exporter pour l'app mobile" / "Importer depuis l'app
  mobile"), au format `.zip`. Couvre les recettes (avec leurs photos),
  les ingrédients connus, le garde-manger et les personnalisations
  (allergènes, prix, substituts). Le planning hebdomadaire, les menus
  et les listes de courses enregistrées ne sont pas encore inclus dans
  ce format partagé — différences de conception trop profondes entre
  les deux applications pour une correspondance fiable.
- **Limites de taille pour une restauration** : avertissement à 50 Mo,
  refus au-delà de 100 Mo — jusqu'ici totalement absentes.

## Comment vérifier la version

Le numéro de version s'affiche dans le titre de la fenêtre principale
au lancement de l'application.

## Vérifications effectuées sur cette version corrigée

- Comparaison ligne par ligne entre votre vrai fichier 1.2.2 et le
  fichier précédemment livré : confirmé que la seule différence était
  le nom de l'application, aucune fonctionnalité manquante.
- Toutes les fonctions testées à nouveau sur la bonne base : migration
  d'identifiant (stable d'un chargement à l'autre), export/import au
  format partagé (recette avec photo, ingrédients, garde-manger,
  personnalisations), limite de taille (refus correct au-delà de
  100 Mo).
- Import d'une vraie archive produite par la vraie application mobile
  vérifié à nouveau sur cette bonne base : recette, ingrédients et
  photo (identique octet pour octet) correctement importés.

## Ce qui n'a toujours pas pu être testé

Le câblage de l'interface graphique (les deux nouveaux boutons, les
messages d'erreur) n'a pas pu être testé visuellement — aucun
environnement graphique disponible dans cet environnement de
développement. La logique sous-jacente a en revanche été testée en
profondeur, comme décrit ci-dessus.

## Fichiers inclus dans cette archive (25 fichiers, ensemble complet)

- `main.py` / `main.pyw` — application (identiques, `.pyw` évite la
  fenêtre console noire au lancement)
- Tous les fichiers de données et de distribution de votre archive
  d'origine : bases d'ingrédients, allergènes, valeurs nutritionnelles,
  substitutions, traductions, drapeaux, icône, script de construction
  de l'exécutable, installateur, documentation

Les données personnelles (recettes, garde-manger, réglages...) ne sont
PAS incluses dans cette archive — elles restent dans votre dossier
d'installation existant. Remplacez simplement les fichiers de cette
archive par-dessus les vôtres.
