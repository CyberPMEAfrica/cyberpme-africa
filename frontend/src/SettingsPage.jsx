export default function SettingsPage({ apiUrl }) {
  return (
    <section className="page-section">
      <div className="page-heading"><div><p className="eyebrow">CONFIGURATION</p><h2>Paramètres</h2><p>Informations non sensibles sur l’environnement CyberPME.</p></div></div>
      <div className="settings-grid">
        <article><span>API utilisée</span><strong>{apiUrl}</strong><p>Adresse du backend utilisée par le dashboard.</p></article>
        <article><span>Actualisation</span><strong>10 secondes</strong><p>Fréquence de synchronisation automatique des données.</p></article>
        <article><span>Mode</span><strong>Développement local</strong><p>Les secrets restent dans le fichier .env et ne sont jamais affichés ici.</p></article>
      </div>
    </section>
  );
}
