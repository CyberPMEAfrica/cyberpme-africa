# Kit de présentation — CyberPME Africa

Les trois visuels sont conçus en format 16:9 (`1920 × 1080`) et peuvent être
insérés directement dans PowerPoint, Google Slides ou affichés dans un
navigateur. Le format SVG reste net sur un vidéoprojecteur, même après zoom.

## 1. Vue globale du SaaS

Fichier : `01-vue-globale-cyberpme.svg`

Message à faire passer :

> CyberPME Africa réunit la supervision, l'audit et la réponse aux incidents
> dans une plateforme unique, accessible aux PME sans imposer une
> infrastructure particulière.

Parcours oral conseillé :

1. partir de l'équipe et des actifs de la PME, à gauche ;
2. présenter les six capacités centrales ;
3. terminer par les quatre bénéfices métier à droite ;
4. insister sur l'isolation des données de chaque entreprise.

## 2. Maquette d'architecture technique

Fichier : `02-architecture-technique-cyberpme.svg`

Message à faire passer :

> Les agents et capteurs restent dans l'infrastructure cliente. Ils envoient
> uniquement des données authentifiées vers une API SaaS multi-tenant.

La légende distingue :

- vert : fonctionnalité déjà opérationnelle ;
- jaune pointillé : évolution prévue avant la production.

Cette distinction évite de présenter comme terminé ce qui appartient encore à
la feuille de route.

## 3. Séquence de traitement d'un incident

Fichier : `03-sequence-incident-cyberpme.svg`

Message à faire passer :

> Une alerte technique devient une action compréhensible, attribuée et
> documentée.

Le scénario correspond au test réel effectué dans le laboratoire :

1. plusieurs échecs SSH sont détectés ;
2. Wazuh déclenche la règle `5712` ;
3. l'adaptateur produit un événement CyberPME commun ;
4. le jeton identifie la PME destinataire ;
5. un analyste prend en charge puis clôture l'incident ;
6. aucun blocage n'est exécuté automatiquement.

## Pitch de 45 secondes

> Les PME africaines disposent rarement d'une équipe SOC complète, alors
> qu'elles exploitent déjà des serveurs, des applications et des données
> critiques. CyberPME Africa centralise la santé des systèmes, les audits
> réseau, les certificats, les sauvegardes et les événements de sécurité.
> Chaque entreprise conserve un espace isolé et peut connecter ses outils
> existants, comme Wazuh. La plateforme transforme ensuite les alertes
> techniques en incidents prioritaires, assignés et documentés. Notre objectif
> est de rendre une cybersécurité structurée accessible, adaptable et
> exploitable par les PME.

## Formulation prudente pour la conférence

Dire :

- « prototype avancé validé dans un laboratoire réel » ;
- « architecture conçue pour être indépendante de l'infrastructure client » ;
- « Wazuh est déjà intégré, Suricata fait partie de la prochaine étape » ;
- « le mode actuel détecte et recommande, sans blocage automatique ».

Éviter pour le moment :

- « produit déjà prêt pour toutes les productions » ;
- « IPS entièrement automatique » ;
- « conformité garantie » ;
- « intelligence artificielle déjà intégrée ».
