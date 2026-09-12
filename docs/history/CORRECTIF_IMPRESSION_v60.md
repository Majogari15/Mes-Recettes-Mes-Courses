# Correction impression Windows — build 60

Les boutons d’impression de recette, liste de courses, planning et menu
utilisent maintenant une boîte d’imprimante Windows et un rendu PDF intégré.
Le lecteur PDF par défaut ne sert plus au chemin normal d’impression.

Si l’utilisateur clique sur Annuler dans la boîte Windows, aucun lecteur PDF
n’est ouvert et aucun faux succès n’est affiché. En cas de refus du pilote ou
d’erreur du moteur, le PDF reste conservé et l’application demande avant de
l’ouvrir manuellement.

Avec main.pyw, installez les dépendances avec `python -m pip install -r
requirements.txt`. Dans l’exécutable construit par `Construire_le_exe.bat`,
`pypdfium2` et son moteur natif sont inclus.

La validation automatisée compte 160 tests. Le dialogue et le pilote
Windows n’étant pas disponibles dans cet environnement, testez une page,
un document de plusieurs pages et l’annulation sur votre ordinateur.
