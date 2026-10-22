# Matrice indicative — PCI DSS, NIST CSF, ISO/IEC 27001–27002

Date : 22 octobre 2026. Document de préparation, pas attestation de conformité.

## Référentiels et périmètre

- PCI DSS v4.0.1 : pertinent si le service entre dans le périmètre d’un environnement de données de cartes ou peut affecter sa sécurité. CyberPME ne doit pas collecter de PAN, CVV ou données d’authentification de carte dans les métriques, rapports ou journaux. Faire déterminer le périmètre par le client et un professionnel qualifié avant de parler de conformité PCI.
- NIST CSF 2.0 : cadre de gestion du risque structuré en Govern, Identify, Protect, Detect, Respond, Recover ; ce n’est pas une certification produit.
- ISO/IEC 27001:2022 : exigences d’un SMSI organisationnel. Une éventuelle certification concerne un organisme et son périmètre, pas simplement le code d’une application.
- ISO/IEC 27002:2022 : guide de mesures et de mise en œuvre. Les rapprochements ci-dessous sont indicatifs, à revoir sur les textes normatifs autorisés et l’analyse de risque du périmètre.

## Contrôles, preuves et travaux organisationnels

| Sujet | NIST CSF 2.0 | PCI DSS — familles pertinentes à évaluer | ISO/IEC 27001 Annexe A / 27002 — thèmes indicatifs | Code / preuve disponible | Encore nécessaire |
|---|---|---|---|---|---|
| Gouvernance et risques | GOVERN | 12, politiques et responsabilités | Gouvernance, risques, relations fournisseurs | Ce dossier et recette pilote | Responsable désigné, inventaire fournisseurs, analyse de risques, engagements client, audit interne et revue de direction |
| Actifs et périmètre | IDENTIFY | 2, configurations ; 12, périmètre | Inventaire, configuration, séparation des environnements | Organisations et serveurs inventoriés | Classification des données, cartographie des flux réels, contrats hébergeurs, registre des risques |
| Identité et accès | PROTECT | 7–8, besoin d’en connaître et authentification | Gestion des identités, droits, authentification sécurisée | Rôles, isolation des tenants, MFA TOTP, jetons individuels, révocation, tests négatifs | Revue périodique des accès, départs des collaborateurs, MFA des consoles fournisseurs, procédure de récupération ; étudier FIDO2 |
| Moindre privilège | PROTECT | 2 et 7 | Droits privilégiés, configuration sécurisée | Agent monitoring sans tâches et service Linux sans capacités | Recette OS réel, contrôle des comptes et permissions effectives, séparation des clés/données |
| Transport et sessions | PROTECT | 4 et 8, selon périmètre | Cryptographie, sécurité réseau, contrôle d’accès | HTTPS agent, cookies protégés, CSRF, CSP, DNS épinglé | TLS et en-têtes en production, configuration proxy, gestion et rotation des secrets, test de pénétration |
| Développement et vulnérabilités | PROTECT / IDENTIFY | 6 et 11 | Développement sécurisé, tests de sécurité, gestion des vulnérabilités | Audits dépendances, verrou npm, CI, tests de régression | Délais de correction, inventaire complet des versions réellement déployées/SBOM, analyse des images et du système, revue indépendante |
| Journalisation et détection | DETECT | 10 et 11 | Journalisation, surveillance, synchronisation temporelle | Journal d’actions, tentatives échouées, alertes de métriques et événements IDS | Export hors base applicative, intégrité/immutabilité, rétention, contrôle des horloges, couverture et procédures de revue |
| Réponse | RESPOND | 12, réponse aux incidents | Gestion des incidents et collecte des preuves | Révocation d’agent, actions administrées séparées | Astreinte, escalade, procédure client, exercice de crise, conservation de preuves et notifications applicables |
| Continuité | RECOVER | 12 et exigences applicables au périmètre | Sauvegardes, préparation à la continuité | Fonctionnalités Restic existantes, désactivées en monitoring | Sauvegarde SaaS distincte, restauration réellement testée, RPO/RTO approuvés, exercice de reprise |

Les en-têtes web ou la MFA ne démontrent pas à eux seuls la conformité à une exigence entière. En particulier, l’expiration absolue des sessions ne démontre pas un verrouillage après inactivité ; les rafraîchissements automatiques ne doivent pas être utilisés comme preuve d’activité humaine. Une analyse spécifique des exigences de session PCI reste ouverte si PCI s’applique.

## Registre minimal de preuves pour le séminaire

1. Révision exacte du code et du déploiement, date, responsables, résultat CI.
2. Rapports de tests et d’audit de dépendances pour cette révision ; conserver aussi les échecs et corrections.
3. Schéma des flux : navigateur → proxy frontend → API → base ; agent → API HTTPS, aucune connexion entrante initiée par le SaaS vers le VPS.
4. Démonstration sur une organisation pilote sans données client : connexion MFA, métriques, redémarrage, rejet d’une tâche interdite et révocation.
5. Registre des limites connues et feuille de route ; ne pas afficher de mot de passe, jeton, secret MFA, clé de chiffrement ou données identifiantes du client.

Phrase de présentation recommandée : « CyberPME met en œuvre un socle de contrôles techniques, avec une démarche d’alignement sur NIST CSF 2.0 et ISO/IEC 27001–27002. L’applicabilité et l’évaluation PCI DSS sont à déterminer selon le périmètre du client. »

## Sources primaires consultées

- PCI SSC, bibliothèque officielle et PCI DSS : https://www.pcisecuritystandards.org/document_library/ ; https://www.pcisecuritystandards.org/standards/pci-dss/
- NIST CSWP 29, CSF 2.0 : https://csrc.nist.gov/pubs/cswp/29/the-nist-cybersecurity-framework-csf-20/final
- ISO/IEC 27001:2022 : https://www.iso.org/standard/27001
- ISO/IEC 27002:2022 : https://www.iso.org/standard/75652.html
- OWASP Authentication Cheat Sheet : https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet : https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

Pour une déclaration formelle : consulter les textes applicables complets, définir une déclaration d’applicabilité et faire évaluer le périmètre par les intervenants compétents. Aucun logo de certification ne doit être ajouté à l’interface ou aux supports sans justification officielle.
