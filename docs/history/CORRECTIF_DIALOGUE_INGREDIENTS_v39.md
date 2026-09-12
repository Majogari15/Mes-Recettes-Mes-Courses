# Correctif du dialogue des ingrédients inconnus — build 39

Lors de l'enregistrement d'une recette contenant un ingrédient inconnu, la
fenêtre de résolution appelait la fonction de mesure de l'écran sans lui
transmettre la fenêtre concernée. L'exception était capturée et affichée par
`main.pyw`, d'où le message signalé sous Windows.

L'appel transmet maintenant `self` à `get_usable_screen_height`. Un test ciblé
vérifie également qu'aucun appel sans argument ne subsiste dans le constructeur
du dialogue.
