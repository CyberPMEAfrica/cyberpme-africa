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
