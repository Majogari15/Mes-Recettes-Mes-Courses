# Rapport import — build 77 / version 1.6.30

Base GitHub : main e9a6c02113f08538acef3ef1636fff7af0c6eb2a, dernière référence vérifiée pendant cette intervention. Aucun envoi sur GitHub.

## Corrections

- Unités EN/ES/DE reconnues : cups, tbsp, tsp, lata, diente, EL, TL, Prise, etc. Cups, oz et lb restent dans leur unité d’origine, sans conversion arbitraire en grammes.
- Rattachement exact aux traductions du dictionnaire et correspondances explicites pour les ingrédients courants. Les précisions sont conservées ; les alternatives et mentions alimentaires restrictives ne sont pas effacées.
- Allergènes retrouvés dans les cinq recettes étrangères importées. Une absence de détection ne garantit pas une absence d’allergène.
- Makes 12 et les rendements en pièces sont signalés ; le nombre de personnes reste à confirmer. Les quantités totales sont conservées avec la valeur provisoire du formulaire.
- Titres anglais/espagnols/allemands reconnus exclus des ingrédients, catégories multilingues enrichies, conseils identifiables et phrases explicites de repos conservés dans les notes.
- Temps total structuré conservé en note lorsque préparation/cuisson manquent, sans inventer leur répartition ni déduire un repos du temps total.
- Adresse finale conservée après redirection et avertissement lors d’un changement de domaine. Quelques unités non prises en charge produisent un avertissement ciblé.
- Complément des ingrédients HTML, dédoublonnage, avertissement pour œufs mentionnés dans les étapes et repli microdonnées conservés. Détection des œufs dans les étapes étendue EN/ES/DE.

## Validation

228 tests exécutés : 219 réussis, 9 ignorés. Les 7 nouveaux tests couvrent plusieurs cas chacun : unités des quatre langues, allergènes et exclusions, rendements et recalcul, sections, catégories/repos, redirections, traductions des avertissements.
Un test antérieur a été adapté à l’ajout volontaire du temps total en note ; il continue de vérifier qu’aucun repos n’est inventé.
Comparaison v76/v77 sur les mêmes cinq pages françaises téléchargées : noms, ingrédients, quantités, personnes, étapes, allergènes, catégories, difficulté et temps identiques ; toutes les notes antérieures sont conservées. Seul ajout attendu : temps total de la salade Mes Recettes Faciles.
Les fonctions _MicrodataRecipeParser et detect_tesseract sont identiques à la base GitHub. Les scripts d’installation ne changent ici que de version.

## Essais en ligne

Une URL par entrée de liste, avec téléchargement direct et récupération de photo. Marmiton figure dans les deux listes : 20 essais pour 19 sites distincts. Les imports sont évalués via le moteur Python, sans validation interactive Windows.

### Liste mondiale

| Site et recette testée | Résultat |
|---|---|
| [Allrecipes](https://www.allrecipes.com/recipe/21014/good-old-fashioned-pancakes/) | Le site a répondu avec une erreur HTTP 402. Essayez d’ouvrir le lien dans votre navigateur. |
| [Cookpad](https://cookpad.com/es/recetas/26528760) | Import et photo récupérés |
| [BBC Good Food](https://www.bbcgoodfood.com/recipes/easy-pancakes) | Import et photo récupérés |
| [Chefkoch](https://www.chefkoch.de/rezepte/1692201277528566/Die-schnellsten-und-besten-Muffins-ueberhaupt.html) | Le site a répondu avec une erreur HTTP 403. Essayez d’ouvrir le lien dans votre navigateur. |
| [Food Network](https://www.foodnetwork.com/recipes/food-network-kitchen/pancakes-recipe-1913844) | Import et photo récupérés |
| [Serious Eats](https://www.seriouseats.com/light-and-fluffy-pancakes-recipe) | Le site a répondu avec une erreur HTTP 402. Essayez d’ouvrir le lien dans votre navigateur. |
| [NYT Cooking](https://cooking.nytimes.com/recipes/1893-everyday-pancakes) | Le site n’a pas répondu dans le délai prévu. Réessayez plus tard ou ouvrez le lien dans votre navigateur. |
| [Marmiton](https://www.marmiton.org/recettes/recette_gateau-au-yaourt-facile_73370.aspx) | Le site n’a pas répondu dans le délai prévu. Réessayez plus tard ou ouvrez le lien dans votre navigateur. |
| [Directo al Paladar](https://www.directoalpaladar.com/postres/flan-cafe-facil-delicioso-esta-mejor-receta-que-vas-a-encontrar-1) | Import et photo récupérés |
| [Tasty](https://tasty.co/recipe/fluffy-perfect-pancakes) | Import et photo récupérés |

### Liste française

| Site et recette testée | Résultat |
|---|---|
| [Marmiton](https://www.marmiton.org/recettes/recette_gateau-au-yaourt-facile_73370.aspx) | Le site n’a pas répondu dans le délai prévu. Réessayez plus tard ou ouvrez le lien dans votre navigateur. |
| [Cuisine AZ](https://www.cuisineaz.com/recettes/crepe-facile-78347.aspx) | Le site n’a pas répondu dans le délai prévu. Réessayez plus tard ou ouvrez le lien dans votre navigateur. |
| [Cuisine Actuelle](https://www.cuisineactuelle.fr/recettes/tarte-tomates-courgettes-300698) | Le site n’a pas répondu dans le délai prévu. Réessayez plus tard ou ouvrez le lien dans votre navigateur. |
| [750g](https://www.750g.com/gateau-au-yaourt-moelleux-r205119.htm) | Import et photo récupérés |
| [Papilles et Pupilles](https://www.papillesetpupilles.fr/2011/01/crepes-faciles.html/) | Le site a répondu avec une erreur HTTP 403. Essayez d’ouvrir le lien dans votre navigateur. |
| [Chef Simon](https://chefsimon.com/gourmets/chef-simon/recettes/la-pate-a-crepes) | Import et photo récupérés |
| [La Cuisine de Bernard](https://lacuisinedebernard.com/cookies-sans-gluten-au-chocolat/) | Le site a répondu avec une erreur HTTP 403. Essayez d’ouvrir le lien dans votre navigateur. |
| [Hervé Cuisine](https://www.hervecuisine.com/recette/crepes-de-la-chandeleur/) | Import et photo récupérés |
| [Clem Foodie](https://clemfoodie.com/2025/08/24/tarte-facile-au-fromage-et-tomates/) | Import et photo récupérés |
| [Mes Recettes Faciles](https://www.mesrecettesfaciles.fr/recipe/salade-de-figues-et-fromage-frais) | Import et photo récupérés |

## Constats et limites

- BBC Good Food : quantité d’huile en cuillère à soupe, allergènes gluten/lactose/œufs, rendement Makes 12 signalé et repos facultatif conservé.
- Tasty : cups et tablespoons reconnus ; gluten/lactose/œufs détectés ; 4 pancakes distingués des personnes.
- Directo al Paladar : œufs/lactose, catégorie Dessert et attente jusqu’au lendemain retrouvés.
- Cookpad : boîte et gousse reconnus, lactose du fromage retrouvé. Les 30 minutes affichées sur la page ne sont pas fournies dans les temps structurés de cette recette : préparation/cuisson restent à compléter. Certains ingrédients composés restent dans la langue d’origine.
- Food Network : recette britannique reçue après redirection, unités corrigées et titres de sections exclus des aliments. Vérifier le titre de la recette reçue. Les groupes ne sont pas recréés comme sections éditables dans le formulaire.
- Les notes ne sont récupérées que lorsqu’elles sont identifiables comme notes de recette ; aucun prélèvement général dans les commentaires ou le texte éditorial.
- Les refus HTTP 402/403 et délais dépassés persistent. Aucun contournement ni service tiers ajouté. Les sites inaccessibles ne peuvent pas être déclarés validés sans régression.
- Allemand : cas automatisés réussis, mais pas de validation en ligne Chefkoch (403).
- 750g : la liste source ne fournit toujours pas les œufs mentionnés dans les étapes ; avertissement conservé sans ajout automatique de quantité.
- Le ZIP contient le projet source prêt à reconstruire, pas un EXE/MSIX compilé et testé sous Windows.

Confiance : élevée sur les cas reproduits et les tests automatisés ; couverture partielle des sites et des variantes de recettes.
