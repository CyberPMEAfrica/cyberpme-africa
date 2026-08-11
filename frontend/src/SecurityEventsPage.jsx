import { useState } from "react";
import "./scanner.css";

const severityLabels = { low: "Faible", medium: "Moyenne", high: "Élevée", critical: "Critique" };
const incidentLabels = { new: "Nouveau", acknowledged: "Pris en charge", resolved: "Résolu", active: "Nouveau" };
const sourceLabels = { wazuh: "Wazuh", suricata: "Suricata", agent: "Agent", other: "Autre" };

function formatEventDate(value) {
  return value ? new Date(value).toLocaleString("fr-FR") : "—";
}

export default function SecurityEventsPage({ apiUrl, token, events, connectors, servers, currentUser, onCreated }) {
  const active = events.filter(event => event.status !== "resolved");
  const [name, setName] = useState("");
  const [connectorType, setConnectorType] = useState("wazuh");
  const [serverId, setServerId] = useState(servers[0]?.id || "");
  const [created, setCreated] = useState(null);
  const [rotatingId, setRotatingId] = useState("");
  const [gracePeriodMinutes, setGracePeriodMinutes] = useState(60);
  const [message, setMessage] = useState("");
  const [incidentFilter, setIncidentFilter] = useState("open");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [eventQuery, setEventQuery] = useState("");
  const [resolvingId, setResolvingId] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const canManage = ["owner", "admin"].includes(currentUser.role);
  const canHandle = ["owner", "admin", "analyst"].includes(currentUser.role);
  const filteredEvents = events.filter(event => {
    const matchesIncident = incidentFilter === "all"
      || (incidentFilter === "open" && event.status !== "resolved")
      || event.status === incidentFilter;
    const matchesSource = sourceFilter === "all" || event.source === sourceFilter;
    const matchesSeverity = severityFilter === "all" || event.severity === severityFilter;
    const normalizedQuery = eventQuery.trim().toLocaleLowerCase("fr-FR");
    const searchableText = [
      event.title,
      event.description,
      event.server_name,
      event.source,
      event.category,
      event.source_ip,
      event.destination_ip,
      event.rule_id,
    ].filter(Boolean).join(" ").toLocaleLowerCase("fr-FR");
    return matchesIncident
      && matchesSource
      && matchesSeverity
      && (!normalizedQuery || searchableText.includes(normalizedQuery));
  });

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

  async function rotateToken(connectorId) {
    setMessage("");
    const response = await fetch(`${apiUrl}/api/v1/ids-connectors/${connectorId}/rotate-token`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ grace_period_minutes: Number(gracePeriodMinutes) }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      setMessage(error.detail || "Impossible de renouveler le jeton.");
      return;
    }
    setCreated(await response.json());
    setRotatingId("");
    setMessage("Jeton renouvelé. Copiez le nouveau secret avant de reconfigurer le collecteur.");
    onCreated();
  }

  async function revokePreviousToken(connectorId) {
    if (!window.confirm("Terminer la transition et révoquer immédiatement l’ancien jeton ?")) return;
    const response = await fetch(`${apiUrl}/api/v1/ids-connectors/${connectorId}/previous-token`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      setMessage(error.detail || "Impossible de révoquer l’ancien jeton.");
      return;
    }
    setMessage("Transition terminée : seul le nouveau jeton est désormais accepté.");
    onCreated();
  }

  async function updateIncident(eventId, status, note = null) {
    const response = await fetch(`${apiUrl}/api/v1/security-events/${eventId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ status, resolution_note: note }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      setMessage(error.detail || "Impossible de mettre à jour l’incident.");
      return;
    }
    setResolvingId("");
    setResolutionNote("");
    setMessage("");
    onCreated();
  }

  return <section className="scanner">
    <div className="section-heading">
      <div><p className="eyebrow">DÉTECTION ET RÉPONSE</p><h2>IDS / IPS</h2></div>
      <span className="safe-mode">Mode détection · aucun blocage automatique</span>
    </div>
    <div className="backup-summary">
      <article><span>Incidents ouverts</span><strong>{active.length}</strong></article>
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
          <strong>{created.token_rotated_at ? "Nouveau jeton à conserver maintenant" : "Jeton à conserver maintenant"}</strong>
          <code>{created.ingest_token}</code>
          <small>URL : {apiUrl}{created.ingest_path}</small>
          {created.previous_token_expires_at && <small>Ancien jeton accepté jusqu’au {new Date(created.previous_token_expires_at).toLocaleString("fr-FR")}.</small>}
        </div>}
        <div className="connector-list">
          {connectors.length ? connectors.map(connector => {
            const transitionActive = connector.previous_token_expires_at
              && new Date(connector.previous_token_expires_at).getTime() > Date.now();
            return <article className="connector-card" key={connector.id}>
              <div className="connector-identity">
                <h3>{connector.name}</h3>
                <p>{connector.connector_type.toUpperCase()} · {connector.server_name}</p>
                <small>{connector.last_event_at ? `Dernier événement : ${new Date(connector.last_event_at).toLocaleString("fr-FR")}` : "En attente du premier événement"}</small>
                {connector.token_rotated_at && <small>Dernier renouvellement : {new Date(connector.token_rotated_at).toLocaleString("fr-FR")}</small>}
                {transitionActive && <small className="rotation-active">Transition active jusqu’au {new Date(connector.previous_token_expires_at).toLocaleString("fr-FR")}</small>}
              </div>
              <span className="scan-status completed">Actif</span>
              {canManage && <div className="connector-actions">
                <button className="secondary-button" onClick={() => setRotatingId(rotatingId === connector.id ? "" : connector.id)}>Renouveler</button>
                {transitionActive && <button className="transition-button" onClick={() => revokePreviousToken(connector.id)}>Terminer la transition</button>}
                <button className="danger-button" onClick={() => remove(connector.id)}>Révoquer</button>
              </div>}
              {rotatingId === connector.id && <div className="token-rotation-form">
                <div>
                  <strong>Renouveler le jeton</strong>
                  <small>L’ancien jeton restera temporairement accepté pour éviter une coupure de collecte.</small>
                </div>
                <label>Période de transition
                  <select value={gracePeriodMinutes} onChange={event => setGracePeriodMinutes(Number(event.target.value))}>
                    <option value={0}>Aucune — révocation immédiate</option>
                    <option value={15}>15 minutes</option>
                    <option value={60}>1 heure</option>
                    <option value={1440}>24 heures</option>
                  </select>
                </label>
                <div>
                  <button onClick={() => rotateToken(connector.id)}>Générer le nouveau jeton</button>
                  <button className="secondary-button" onClick={() => setRotatingId("")}>Annuler</button>
                </div>
              </div>}
            </article>;
          }) : <div className="empty-state"><h3>Aucun connecteur configuré</h3><p>Créez un connecteur Wazuh, Suricata ou générique pour cette organisation.</p></div>}
        </div>
      </div>
    </div>
    <div className="section-heading event-heading">
      <div><p className="eyebrow">ÉVÉNEMENTS NORMALISÉS</p><h2>Historique des détections</h2></div>
    </div>
    <div className="event-filter-bar" aria-label="Filtres des événements de sécurité">
      <label>Recherche<input type="search" value={eventQuery} onChange={event => setEventQuery(event.target.value)} placeholder="Titre, adresse IP, règle…" /></label>
      <label>Technologie<select value={sourceFilter} onChange={event => setSourceFilter(event.target.value)}><option value="all">Toutes</option><option value="wazuh">Wazuh</option><option value="suricata">Suricata</option><option value="agent">Agent</option><option value="other">Autre</option></select></label>
      <label>Gravité<select value={severityFilter} onChange={event => setSeverityFilter(event.target.value)}><option value="all">Toutes</option><option value="critical">Critique</option><option value="high">Élevée</option><option value="medium">Moyenne</option><option value="low">Faible</option></select></label>
      <label>Statut<select value={incidentFilter} onChange={event => setIncidentFilter(event.target.value)}><option value="open">Incidents ouverts</option><option value="new">Nouveaux</option><option value="acknowledged">Pris en charge</option><option value="resolved">Résolus</option><option value="all">Tous</option></select></label>
      <span className="event-filter-count">{filteredEvents.length} résultat{filteredEvents.length > 1 ? "s" : ""}</span>
    </div>
    <div className="security-events">
      {filteredEvents.length ? filteredEvents.map(event => <article className={`security-event ${event.severity} ${event.status}`} key={event.id}>
        <div className="ssl-head">
          <div>
            <h3>{event.title}</h3>
            <small>{event.server_name} · {sourceLabels[event.source] || event.source.toUpperCase()}</small>
            <div className="event-timestamps">
              <span>Détecté le <b>{formatEventDate(event.occurred_at)}</b></span>
              <span>Reçu le <b>{formatEventDate(event.received_at)}</b></span>
            </div>
          </div>
          <div className="incident-badges"><em className={`incident-status ${event.status}`}>{incidentLabels[event.status] || event.status}</em><em className={`event-severity ${event.severity}`}>{severityLabels[event.severity]}</em></div>
        </div>
        <p>{event.description}</p>
        <div className="event-details">
          <span>Catégorie <b>{event.category}</b></span>
          {event.source_ip && <span>Source <b>{event.source_ip}</b></span>}
          {event.destination_ip && <span>Destination <b>{event.destination_ip}</b></span>}
          {event.rule_id && <span>Règle <b>{event.rule_id}</b></span>}
        </div>
        <div className="event-recommendation"><strong>Action recommandée</strong><p>{event.recommendation}</p></div>
        {event.handled_by_email && <p className="incident-owner">Suivi par <strong>{event.handled_by_email}</strong>{event.resolved_at ? ` · Résolu le ${new Date(event.resolved_at).toLocaleString("fr-FR")}` : ""}</p>}
        {event.resolution_note && <div className="resolution-note"><strong>Conclusion</strong><p>{event.resolution_note}</p></div>}
        {canHandle && <div className="incident-actions">
          {(event.status === "new" || event.status === "active") && <button onClick={() => updateIncident(event.id, "acknowledged")}>Prendre en charge</button>}
          {event.status !== "resolved" && <button className="secondary-button" onClick={() => setResolvingId(resolvingId === event.id ? "" : event.id)}>Résoudre</button>}
          {event.status === "resolved" && <button className="secondary-button" onClick={() => updateIncident(event.id, "new", "Incident rouvert pour nouvelle analyse.")}>Rouvrir</button>}
        </div>}
        {resolvingId === event.id && <div className="resolution-form">
          <label>Commentaire de résolution<textarea value={resolutionNote} onChange={item => setResolutionNote(item.target.value)} placeholder="Décrivez la vérification et la correction effectuée." maxLength="2000"/></label>
          <button disabled={resolutionNote.trim().length < 3} onClick={() => updateIncident(event.id, "resolved", resolutionNote)}>Confirmer la résolution</button>
        </div>}
      </article>) : <div className="empty-state"><h3>Aucun événement de sécurité</h3><p>Le collecteur Wazuh/Suricata sera connecté à cette page. Aucun blocage n’est actif.</p></div>}
    </div>
  </section>;
}
