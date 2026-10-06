# Sauvegardes et reponse IDS assistee — agent 0.3

## Perimetre et statut

Cette version ajoute des actions locales explicitement autorisees. Elle ne constitue
pas un IPS autonome : un evenement IDS permet de proposer un blocage, qui doit etre
approuve par un proprietaire ou administrateur. Rien n'est active par defaut.
Les tests automatises utilisent des executants simules ; la validation sur une VM
Linux et une VM Windows jetables est indispensable avant toute activation client.

## Mise en service

1. Sauvegarder la base applicative et appliquer `alembic upgrade head` dans backend.
2. Deployer le backend et le frontend ensemble. Installer l'agent version 0.3.
3. Fusionner la section `operations` de `agent/operations.example.json` dans la
   configuration existante de l'agent, sans remplacer ses identifiants ni son etat.
4. Configurer chaque profil sur le poste, sous controle administrateur. Proteger
   configuration, etat et fichiers secrets : root uniquement sous Linux, SYSTEM
   et administrateurs sous Windows. Ne jamais les placer dans un depot Git.
5. Activer seulement les fonctions testees et redemarrer le processus agent.

Le navigateur ne peut transmettre ni commande libre, ni mot de passe de sauvegarde,
ni chemin de fichiers. Il ne choisit qu'un profil local deja autorise. Un agent sans
section operations continue de fonctionner comme auparavant.

## Sauvegardes chiffrees

Installer Restic >= 0.17 sur le poste et le rendre accessible au compte du service.
Preparer et initialiser manuellement un depot Restic sur un stockage externe a la
machine. Conserver le mot de passe hors machine dans un coffre : sa perte rend les
sauvegardes irrecuperables. L'agent ne cree jamais de depot implicitement.
Utiliser un depot distinct par client. Les snapshots portent une identite composee
du nom de machine et de son identifiant agent, afin de distinguer les noms identiques.

Le profil fichiers exige des dossiers absolus, un depot distinct et un repertoire
de restauration separe. Sous Windows utiliser par exemple `C:/Donnees/Entreprise`
et `D:/TestsRestauration` ; verifier que le compte SYSTEM accede au stockage distant
(les lecteurs reseau d'une session utilisateur ne sont pas necessairement visibles).
Les fichiers ouverts ne beneficient pas d'un snapshot VSS dans cette version.

Pour PostgreSQL : `kind: postgresql`, `sources: []`, `postgres_service`,
`pg_service_file` et `pg_pass_file` designent un service libpq configure localement.
Installer pg_dump compatible avec le serveur et pg_restore. Les fichiers de service
et de mots de passe doivent etre accessibles uniquement au compte de l'agent.
Le dump au format custom est transmis a Restic via stdin-from-command, sans mot de
passe dans la commande ni fichier SQL temporaire.

Dans Sauvegardes, proposer une action en indiquant le profil puis l'approuver.
Un snapshot chiffre est retourne. La restauration de test cree un nouveau dossier
unique et verifie les fichiers. Pour PostgreSQL elle verifie la lecture de l'archive,
mais ne restaure pas une base active : un exercice de restauration SQL dans une base
jetable reste necessaire pour valider une reprise complete.

La planification est un consentement local distinct : `schedule_enabled: true` et
`interval_hours` (1 a 8760). Le premier passage est immediat ; les suivants suivent
le dernier essai.
En cas de panne du SaaS, les sauvegardes locales continuent ; le dernier etat de
supervision est conserve pour transmission au retour du reseau.
La retention n'est appliquee que si `retention_enabled: true` ;
`keep_last` doit etre compris entre 2 et 365. Elle supprime des anciennes versions
du meme hote/profil : la laisser desactivee pendant le pilote.

## Blocage temporaire

Le blocage concerne uniquement une IPv4 publique source d'un evenement IDS du meme
agent. Duree maximale 60 minutes, protection des IP API et des reseaux locaux.
Ajouter dans `protected_networks` les IP publiques du VPN, des administrateurs,
des sauvegardes et des partenaires indispensables avant activation.

Linux : installer nftables et faire valider puis charger MANUELLEMENT la table
dediee fournie dans `agent/cyberpme-guard.nft`, sans effacer les regles existantes.
Le timeout des elements est gere par le noyau. Cette version bloque les nouvelles
connexions TCP entrantes hors ports 22, 3389, 5985 et 5986.

Windows : le compte agent doit disposer des droits pare-feu et planificateur.
Une tache SYSTEM de suppression est creee avant la regle. La regle est temporaire
dans ActiveStore et ne doit pas persister au redemarrage. Les memes ports
administratifs sont exclus. Les connexions existantes peuvent etre affectees.

Le bouton d'annulation demande a l'agent de retirer le blocage ; si le poste est
hors ligne, l'expiration locale reste le recours. Aucun blocage UDP, IPv6, reseau
entier ou automatique sans approbation n'est fourni par cette version.

## Recette obligatoire avant production

- Verifier les permissions analyste/admin et l'isolation entre organisations.
- Sauvegarder un dossier test, modifier ses fichiers puis restaurer le snapshot
  dans un autre dossier ; comparer les contenus et verifier les originaux intacts.
- Tester PostgreSQL dans une base jetable avec des donnees connues.
- Couper le reseau apres execution : le resultat doit etre renvoye sans repetition.
- Interrompre l'agent pendant une action : un resultat incertain exige un examen
  local, pas une repetition automatique.
- Sur VM jetable, verifier refus des IP protegees, blocage d'une IP de test
  autorisee, annulation et expiration agent arrete, puis redemarrage de la VM.
- Verifier une sauvegarde planifiee sous le compte reel du service.

Ne pas utiliser un test de blocage sur la seule connexion d'administration d'un
serveur. Prevoir une console de secours. Le journal applicatif enregistre
proposition, approbation et resultat, pas les secrets de stockage.

## Verification de cette livraison

- Suite backend : 46 tests reussis, migrations comprises.
- Verification ciblee supplementaire des actions : 7 tests reussis (permissions,
  isolation, expiration, validation du resultat, approbation et annulation IDS).
- Agent : 27 tests reussis, avec executants simules pour Restic et le pare-feu,
  et analyse syntaxique du script Windows sans execution de ses commandes.
- Compilation du frontend : reussie.
- Aucun deploiement, changement de pare-feu reel ou sauvegarde de donnees client
  effectue pendant cette verification. Le controle visuel navigateur et la recette
  avec Restic, PostgreSQL et pare-feu reels restent a effectuer en environnement pilote.
