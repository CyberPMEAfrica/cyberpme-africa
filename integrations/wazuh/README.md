# Adaptateur Wazuh CyberPME

Cet adaptateur utilise le module officiel Wazuh Integrator. Il transforme chaque
alerte Wazuh en événement CyberPME normalisé, puis l'envoie au connecteur de
l'organisation concernée.

## Installation

Copier `custom-cyberpme` dans `/var/ossec/integrations/`, puis appliquer :

```bash
sudo chown root:wazuh /var/ossec/integrations/custom-cyberpme
sudo chmod 750 /var/ossec/integrations/custom-cyberpme
```

Le configurateur `configure-cyberpme` automatise ensuite la sauvegarde de
`ossec.conf`, la validation XML et la restauration en cas d'échec. Il demande
l'URL et le jeton sans les inscrire dans l'historique du shell :

```bash
sudo install -o root -g root -m 700 configure-cyberpme /usr/local/sbin/configure-cyberpme
sudo /usr/local/sbin/configure-cyberpme
```

Il ajoute le bloc suivant à l'intérieur de `<ossec_config>` :

```xml
<integration>
  <name>custom-cyberpme</name>
  <hook_url>https://api.example.com/api/v1/ids-connectors/CONNECTOR_ID/events</hook_url>
  <api_key>CONNECTOR_TOKEN</api_key>
  <level>7</level>
  <alert_format>json</alert_format>
  <timeout>10</timeout>
  <retries>3</retries>
</integration>
```

Le niveau `7` limite le bruit initial. Le jeton appartient à une seule
organisation, n'est affiché qu'à sa création et doit rester secret.

Dans un laboratoire VirtualBox en NAT, l'adresse `localhost` affichée par le
navigateur doit être remplacée par l'adresse de la passerelle hôte, par exemple
`10.0.2.2`. En production, l'intégration utilise l'URL HTTPS publique du SaaS.

## Renouvellement du jeton sans interruption

Un propriétaire ou administrateur peut renouveler le jeton depuis
**IDS / IPS → Renouveler**. CyberPME affiche le nouveau jeton une seule fois et
peut maintenir l'ancien pendant 15 minutes, 1 heure ou 24 heures.

Procédure recommandée :

1. choisir une période de transition adaptée à l'accès au serveur Wazuh ;
2. copier immédiatement le nouveau jeton ;
3. relancer `sudo /usr/local/sbin/configure-cyberpme` avec la même URL
   d'ingestion et le nouveau jeton ;
4. vérifier dans CyberPME que la date du dernier événement se met à jour ;
5. cliquer sur **Terminer la transition** pour révoquer l'ancien jeton avant
   l'expiration prévue.

L'option **Aucune — révocation immédiate** doit être réservée à un jeton
suspecté d'être compromis ou à une intervention où Wazuh peut être reconfiguré
immédiatement. Seuls les hachages des jetons sont conservés par CyberPME.
