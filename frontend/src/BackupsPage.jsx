import "./scanner.css";

function sizeLabel(bytes) {
  if (bytes == null) return "—";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
}

export default function BackupsPage({ checks }) {
  const latest = [...checks].filter((item, index, all) =>
    all.findIndex((candidate) => candidate.server_id === item.server_id && candidate.name === item.name) === index
  );
  return <section className="scanner">
    <div className="section-heading"><div><p className="eyebrow">CONTINUITÉ D’ACTIVITÉ</p><h2>Sauvegardes</h2></div></div>
    <div className="backup-summary">
      <article><span>Contrôles suivis</span><strong>{latest.length}</strong></article>
      <article><span>À jour</span><strong className="good">{latest.filter(x => x.status === "healthy").length}</strong></article>
      <article><span>À corriger</span><strong className="bad">{latest.filter(x => x.status !== "healthy").length}</strong></article>
    </div>
    <div className="backup-grid">
      {latest.length ? latest.map(check => <article className="ssl-card" key={check.id}>
        <div className="ssl-head"><div><h3>{check.name}</h3><small>{check.server_name} · {check.kind === "postgresql" ? "PostgreSQL" : "Fichiers / dossier"}</small></div>
          <em className={`ssl-status ${check.status === "healthy" ? "valid" : "critical"}`}>{check.status === "healthy" ? "À jour" : "Action requise"}</em>
        </div>
        <div className="ssl-metrics">
          <div><span>Dernier succès</span><strong>{check.last_success_at ? new Date(check.last_success_at).toLocaleString("fr-FR") : "Aucun"}</strong></div>
          <div><span>Taille</span><strong>{sizeLabel(check.size_bytes)}</strong></div>
          <div><span>Fréquence attendue</span><strong>{check.max_age_hours} h</strong></div>
        </div>
        <p>{check.error || `Source vérifiée : ${check.source}`}</p>
      </article>) : <div className="empty-state"><h3>Aucun contrôle reçu</h3><p>Configurez les chemins de sauvegarde dans l’agent CyberPME.</p></div>}
    </div>
  </section>;
}
