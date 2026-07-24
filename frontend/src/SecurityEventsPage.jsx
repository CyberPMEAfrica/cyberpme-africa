import "./scanner.css";

const severityLabels = { low: "Faible", medium: "Moyenne", high: "Élevée", critical: "Critique" };

export default function SecurityEventsPage({ events }) {
  const active = events.filter(event => event.status === "active");
  return <section className="scanner">
    <div className="section-heading">
      <div><p className="eyebrow">DÉTECTION ET RÉPONSE</p><h2>IDS / IPS</h2></div>
      <span className="safe-mode">Mode détection · aucun blocage automatique</span>
    </div>
    <div className="backup-summary">
      <article><span>Événements reçus</span><strong>{events.length}</strong></article>
      <article><span>Élevés / critiques</span><strong className={active.some(x => ["high", "critical"].includes(x.severity)) ? "bad" : "good"}>{active.filter(x => ["high", "critical"].includes(x.severity)).length}</strong></article>
      <article><span>Capteurs</span><strong>{new Set(events.map(x => x.server_id)).size}</strong></article>
    </div>
    <div className="security-events">
      {events.length ? events.map(event => <article className={`security-event ${event.severity}`} key={event.id}>
        <div className="ssl-head">
          <div><h3>{event.title}</h3><small>{event.server_name} · {event.source.toUpperCase()} · {new Date(event.occurred_at).toLocaleString("fr-FR")}</small></div>
          <em className={`event-severity ${event.severity}`}>{severityLabels[event.severity]}</em>
        </div>
        <p>{event.description}</p>
        <div className="event-details">
          <span>Catégorie <b>{event.category}</b></span>
          {event.source_ip && <span>Source <b>{event.source_ip}</b></span>}
          {event.destination_ip && <span>Destination <b>{event.destination_ip}</b></span>}
          {event.rule_id && <span>Règle <b>{event.rule_id}</b></span>}
        </div>
        <div className="event-recommendation"><strong>Action recommandée</strong><p>{event.recommendation}</p></div>
      </article>) : <div className="empty-state"><h3>Aucun événement de sécurité</h3><p>Le collecteur Wazuh/Suricata sera connecté à cette page. Aucun blocage n’est actif.</p></div>}
    </div>
  </section>;
}
