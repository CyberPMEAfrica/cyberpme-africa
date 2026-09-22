import { useState } from "react";

const statusLabels = {
  pending: "En attente",
  running: "Analyse en cours",
  completed: "Terminé",
  failed: "Échec",
};

export default function NetworkScanner({ apiUrl, token, scans, currentUser, onCreated }) {
  const [target, setTarget] = useState("192.168.1.0/24");
  const [authorized, setAuthorized] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const latest = scans[0];
  const canRunScan = ["owner", "admin", "analyst"].includes(currentUser.role);
  const hosts = Array.isArray(latest?.results)
    ? latest.results.map((host) => ({
        ...host,
        ports: Array.isArray(host?.ports) ? host.ports : [],
        recommendations: Array.isArray(host?.recommendations) ? host.recommendations : [],
      }))
    : [];

  async function startScan(event) {
    event.preventDefault();
    if (!authorized) {
      setMessage("Confirmez que vous êtes autorisé à auditer ce réseau.");
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/network-scans`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ target }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Impossible de démarrer l’audit.");
      setMessage("Audit démarré. Les résultats seront actualisés automatiquement.");
      await onCreated();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function downloadReport() {
    const response = await fetch(`${apiUrl}/api/v1/network-scans/${latest.id}/report`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) { setMessage("Impossible de télécharger le rapport."); return; }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `audit-reseau-${latest.id}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="scanner">
      <div className="title">
        <div><p className="eyebrow">AUDIT RÉSEAU</p><h2>Scanner de sécurité</h2></div>
        <small>Réseaux IPv4 privés · maximum /24</small>
      </div>
      <div className="scanner-layout">
        <form className="scan-form" onSubmit={startScan}>
          <h3>Nouvel audit autorisé</h3>
          <p>Découvre les équipements et identifie les 100 ports TCP les plus courants.</p>
          <label>
            Réseau à auditer
            <input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="192.168.1.0/24" required />
          </label>
          <label className="authorization">
            <input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
            <span>Je confirme être autorisé à analyser ce réseau.</span>
          </label>
          {!canRunScan && <p className="scan-message">Votre rôle dispose d’un accès en lecture seule.</p>}
          <button type="submit" disabled={submitting || !canRunScan || latest?.status === "pending" || latest?.status === "running"}>
            {submitting ? "Démarrage..." : "Lancer l’audit"}
          </button>
          {message && <p className="scan-message" role="status">{message}</p>}
        </form>

        <div className="scan-results">
          {!latest ? (
            <div className="empty"><h3>Aucun audit réseau</h3><p>Lancez un premier audit sur un réseau que vous administrez.</p></div>
          ) : (
            <>
              <div className="scan-summary">
                <div><span>Dernière cible</span><strong>{latest.target}</strong></div>
                <em className={`scan-status ${latest.status}`}>{statusLabels[latest.status]}</em>
              </div>
              {latest.status === "completed" && (
                <button type="button" className="report-link" onClick={downloadReport}>
                  Télécharger le rapport PDF
                </button>
              )}
              {latest.error && <p className="error">{latest.error}</p>}
              {latest.status === "completed" && !hosts.length && <p className="scan-note">Aucun équipement actif détecté.</p>}
              <div className="scan-hosts">
                {hosts.map((host) => (
                  <article className="scan-host" key={host.ip_address}>
                    <div><h3>{host.hostname || host.ip_address}</h3>{host.hostname && <small>{host.ip_address}</small>}</div>
                    {!host.ports.length ? <p>Aucun port courant ouvert.</p> : (
                      <div className="port-list">
                        {host.ports.map((port) => (
                          <span key={`${port.protocol}-${port.port}`}>
                            <b>{port.port}/{port.protocol}</b> {port.service}{port.product ? ` · ${port.product}` : ""}
                          </span>
                        ))}
                      </div>
                    )}
                    {host.recommendations.length > 0 && (
                      <ul>{host.recommendations.map((recommendation) => <li key={recommendation}>{recommendation}</li>)}</ul>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
