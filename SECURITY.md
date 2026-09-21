# Politique de sécurité

## Versions supportées

Seule la dernière version publiée (voir [`CHANGELOG.md`](CHANGELOG.md) et
[`VERSION.md`](VERSION.md)) reçoit des correctifs de sécurité. Il s'agit
d'une application de bureau à usage personnel, sans version antérieure
maintenue en parallèle.

## Signaler une vulnérabilité

Si vous découvrez une faille de sécurité (par exemple : un chemin de
fichier mal contrôlé, une donnée importée qui pourrait exécuter du code,
une fuite de données personnelles), merci de la signaler de préférence via
l'onglet **Security → Report a vulnerability** de ce dépôt GitHub (rapport
privé), plutôt que par une *issue* publique.

Merci d'indiquer :
- la version de l'application concernée (`VERSION.md`) ;
- les étapes précises pour reproduire le problème ;
- l'impact potentiel (perte de données, exécution de code, etc.).

Il s'agit d'un projet personnel maintenu sur mon temps libre : je ne peux
pas garantir de délai de réponse formel, mais tout signalement sérieux sera
traité en priorité.

## Périmètre concerné

L'application ne dépend d'aucun serveur ni compte en ligne : les données
(recettes, photos, listes de courses) restent en local, à côté de
l'exécutable ou dans `%LocalAppData%\MesRecettesMesCourses` si ce dossier
n'est pas accessible en écriture. Les surfaces les plus sensibles sont donc
celles qui traitent des données venant de l'extérieur :

- l'**import de recette depuis une URL ou une photo** (page web, OCR) ;
- l'**import/restauration d'une sauvegarde** (`.zip` ou `.txt` partagé) ;
- la **lecture d'un QR code** partagé par une autre installation ;
- la **construction et l'installation** de l'exécutable (`Construire_le_exe.bat`,
  `installateur.iss`).

Les dépendances Python sont vérifiées automatiquement à chaque changement
de `requirements.txt` par le workflow `security-audit.yml` (`pip-audit`),
et mises à jour chaque semaine par Dependabot (voir
`.github/dependabot.yml`).
