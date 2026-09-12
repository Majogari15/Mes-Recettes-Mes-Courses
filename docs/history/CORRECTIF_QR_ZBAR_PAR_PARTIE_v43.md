# Correction QR ZBar partie par partie — build 43

Le second lot fourni a permis d'identifier précisément le défaut restant.
ZBar ne choisit pas forcément le même encodage pour toutes les images d'une
même recette. Pour le lot Financiers, la première partie était réencodée comme
du Latin-1 tandis que la seconde transformait notamment `fraîches` en
`fraﾃｮches`, caractéristique d'une interprétation Shift-JIS.

Le build 43 produit donc des candidats séparément pour chaque partie, les
classe selon les traces de mauvais encodage, puis n'accepte la reconstruction
que si elle retrouve exactement le checksum mobile. Le format et la génération
des QR de l'application mobile ne sont pas modifiés.
