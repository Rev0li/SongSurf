# Vitrine SongSurf + Jellyfin — idées pour le portfolio

Note de passage vers la session **portfolio** (refonte de zéro, page publique + preuve de travail). Rien ici n'est décidé : ce sont des pistes à trancher dans ta doc portfolio.

## Contraintes

- **Montrer, jamais offrir** : aucun téléchargement YouTube public, aucun accès à la vraie bibliothèque Jellyfin (droits d'auteur, conditions de YouTube). Les démos tournent sur de la musique libre (Creative Commons).
- **Accès restreint** : bac à sable sur invitation, avec un rôle `demo` à jeton court (≈ 30 min) émis par rev0auth. Côté SongSurf, c'est à faire après la V1 (voir `PLAN_V1.md` › Pistes liées).
- **Identité** (questionnaire Obsidian `revosafe/Mycss/`) : sobre façon Apple, organique, aéré, lofi, rose pâle + turquoise, animations courtes et subtiles, peu de texte.

## Concepts

1. **La run** (Hades) ⭐ : visite en 3 salles, *Trouver* (extension), *Ranger* (métadonnées), *Écouter* (Jellyfin). Chaque salle est une mini-démo jouable avec de fausses données. Fin : « Tu veux ta propre run ? »
2. **Le billet d'accès** ⭐ : le contact prend la forme d'un billet de concert à remplir (prénom, pourquoi). Une fois validé, il devient un lien d'invitation au bac à sable.
3. **Pochette vivante** : l'accueil est une grande pochette générée (formes douces) qui respire au rythme du son. Trois mots, un bouton.
4. **Le voyage d'un titre** : le défilement suit un morceau, de YouTube Music jusqu'au téléphone. Une phrase par étape.
5. **Couches** (Inception) : zoom de couche en couche, appli → NAS → Tailscale → VPS → auth.

Combinaison recommandée : 3 en accueil, 1 comme trailer, 2 comme contact.

## Le son : « monte le son, tu vas kiffer »

- Les navigateurs **bloquent la lecture automatique avec du son** tant que le visiteur n'a pas cliqué. Le son « très bas au départ » ne peut donc pas démarrer tout seul.
- La solution : faire de la phrase **le bouton lui-même**. « Monte le son, tu vas kiffer » est cliquable. Au clic, le son démarre très bas et monte doucement en 2–3 s, sans coupure brusque.
- Avant le clic, montrer le son sans le jouer : un égaliseur ou une onde qui bouge **en silence**, avec la pochette qui respire. On *voit* la musique, on a envie de l'entendre.
- Animation du texte : les lettres ondulent légèrement comme une onde sonore, puis se calment une fois le son lancé et laissent place à un petit bouton muet/volume, toujours visible.
- Accessibilité : respecter `prefers-reduced-motion` (texte fixe), bouton couper le son toujours accessible, rien d'indispensable ne passe par le son.

Variantes de la phrase, du même ton : « Mets ton casque. » · « Ça s'écoute, ça se lit pas. » · « Clique, et laisse tourner. »
