# Import QR multi-parties UTF-8 — build 42

Les trois QR Barramundi transmis sont valides : ils appartiennent au lot
`70968a7b2ddb`, couvrent bien les parties 1 à 3 et leur contenu reconstitué
correspond à la somme de contrôle `12phf2l`.

L'échec venait d'une interprétation ANSI possible des octets UTF-8 par le
lecteur QR Windows. Le texte peut désormais être réparé après réassemblage,
mais uniquement lorsqu'une conversion réversible retrouve exactement la somme
de contrôle originale. Une vraie modification d'un fragment reste refusée.
