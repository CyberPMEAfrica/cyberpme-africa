import { useState } from "react";
import "./scanner.css";

const severityLabels = { low: "Faible", medium: "Moyenne", high: "Élevée", critical: "Critique" };

export default function SecurityEventsPage({ apiUrl, token, events, connectors, servers, currentUser, onCreated }) {
  const active = events.filter(event => event.status === "active");
  const [name, setName] = useState("");
  const [connectorType, setConnectorType] = useState("wazuh");
  const [serverId, setServerId] = useState(servers[0]?.id || "");
  const [created, setCreated] = useState(null);
  const [message, setMessage] = useState("");
  const canManage = ["owner", "admin"].includes(currentUser.role);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    const response = await fetch(`${apiUrl}/api/v1/ids-connectors`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ name, connector_type: connectorType, server_id: serverId }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      setMessage(error.detail || "Impossible de créer le connecteur.");
      return;
    }
    setCreated(await response.json());
    setName("");
    setMessage("Connecteur créé. Copiez maintenant le jeton : il ne sera plus affiché.");
    onCreated();
  }

  async function remove(connectorId) {
    if (!window.confirm("Supprimer ce connecteur et révoquer immédiatement son jeton ?")) return;
    const response = await fetch(`${apiUrl}/api/v1/ids-connectors/${connectorId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      if (created?.id === connectorId) setCreated(null);
      onCreated();
    }
  }

  return <section className="scanner">
    <div className="section-heading">
      <div><p className="eyebrow">DÉTECTION ET RÉPONSE</p><h2>IDS / IPS</h2></div>
      <span className="safe-mode">Mode détection · aucun blocage automatique</span>
    </div>
    <div className="backup-summary">
      <article><span>Événements reçus</span><strong>{events.length}</strong></article>
      <article><span>Élevés / critiques</span><strong className={active.some(x => ["high", "critical"].includes(x.severity)) ? "bad" : "good"}>{active.filter(x => ["high", "critical"].includes(x.severity)).length}</strong></article>
      <article><span>Connecteurs actifs</span><strong>{connectors.filter(x => x.status === "active").length}</strong></article>
    </div>
    <div className="connector-layout">
      <form className="scan-form" onSubmit={submit}>
        <h3>Nouveau connecteur</h3>
        <p>Créez un point d’entrée propre à cette PME. Le SIEM enverra ensuite ses alertes normalisées vers CyberPME.</p>
        <label>Nom du connecteur<input value={name} onChange={event => setName(event.target.value)} placeholder="Wazuh agence principale" required disabled={!canManage}/></label>
        <label>Technologie<select value={connectorType} onChange={event => setConnectorType(event.target.value)} disabled={!canManage}><option value="wazuh">Wazuh</option><option value="suricata">Suricata</option><option value="other">Autre SIEM</option></select></label>
        <label>Équipement associé<select value={serverId} onChange={event => setServerId(event.target.value)} required disabled={!canManage}><option value="">Choisir un serveur</option>{servers.map(server => <option value={server.id} key={server.id}>{server.name}</option>)}</select></label>
        <button disabled={!canManage || !servers.length}>Créer le connecteur</button>
        {!canManage && <p className="scan-message">Un propriétaire ou administrateur doit configurer les connecteurs.</p>}
        {!servers.length && <p className="scan-message">Enregistrez d’abord un serveur ou capteur.</p>}
        {message && <p className="scan-message">{message}</p>}
      </form>
      <div className="scan-results">
        {created && <div className="connector-secret">
          <strong>Jeton à conserver maintenant</strong>
          <code>{created.ingest_token}</code>
          <small>URL : {apiUrl}{created.ingest_path}</small>
        </div>}
        <div className="connector-list">
          {connectors.length ? connectors.map(connector => <article key={connector.id}>
            <div><h3>{connector.name}</h3><p>{connector.connector_type.toUpperCase()} · {connector.server_name}</p><small>{connector.last_event_at ? `Dernier événement : ${new Date(connector.last_event_at).toLocaleString("fr-FR")}` : "En attente du premier événement"}</small></div>
            <span className="scan-status completed">Actif</span>
            {canManage && <button className="danger-button" onClick={() => remove(connector.id)}>Révoquer</button>}
          </article>) : <div className="empty-state"><h3>Aucun connecteur configuré</h3><p>Créez un connecteur Wazuh, Suricata ou générique pour cette organisation.</p></div>}
        </div>
      </div>
    </div>
    <div className="section-heading event-heading"><div><p className="eyebrow">ÉVÉNEMENTS NORMALISÉS</p><h2>Détections récentes</h2></div></div>
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
