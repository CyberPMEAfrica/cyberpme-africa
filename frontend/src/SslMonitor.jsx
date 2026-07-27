import { useState } from "react";

const statusLabels = {
  valid: "Valide",
  warning: "Expire bientôt",
  expired: "Expiré",
  critical: "Non fiable",
  failed: "Échec",
};

function formatDate(value) {
  return value ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(value)) : "—";
}

export default function SslMonitor({ apiUrl, token, checks, onCreated }) {
  const [hostname, setHostname] = useState("");
  const [port, setPort] = useState("443");
  const [scanKey, setScanKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  async function runCheck(event) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/ssl-checks`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Scan-Key": scanKey, Authorization: `Bearer ${token}` },
        body: JSON.stringify({ hostname, port: Number(port) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Impossible de vérifier ce certificat.");
      setMessage("Vérification terminée.");
      await onCreated();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="ssl-monitor">
      <div className="title">
        <div><p className="eyebrow">CERTIFICATS</p><h2>Surveillance SSL/TLS</h2></div>
        <small>Domaines publics · ports 443 et 8443</small>
      </div>
      <div className="ssl-layout">
        <form className="ssl-form" onSubmit={runCheck}>
          <h3>Vérifier un domaine</h3>
          <p>Contrôle la confiance, l’expiration et les paramètres TLS du certificat présenté.</p>
          <label>
            Nom de domaine
            <input value={hostname} onChange={(event) => setHostname(event.target.value)} placeholder="example.com" required />
          </label>
          <label>
            Port TLS
            <select value={port} onChange={(event) => setPort(event.target.value)}>
              <option value="443">443</option>
              <option value="8443">8443</option>
            </select>
          </label>
          <label>
            Clé d’audit
            <input type="password" value={scanKey} onChange={(event) => setScanKey(event.target.value)} required autoComplete="off" />
          </label>
          <button type="submit" disabled={submitting}>{submitting ? "Vérification..." : "Vérifier le certificat"}</button>
          {message && <p className="ssl-message" role="status">{message}</p>}
        </form>

        <div className="ssl-results">
          {!checks.length ? (
            <div className="empty"><h3>Aucun certificat vérifié</h3><p>Ajoutez un domaine public pour commencer la surveillance.</p></div>
          ) : (
            <div className="ssl-history">
              {checks.slice(0, 6).map((check) => (
                <article className="ssl-card" key={check.id}>
                  <div className="ssl-head">
                    <div><h3>{check.hostname}:{check.port}</h3><small>Contrôlé le {formatDate(check.checked_at)}</small></div>
                    <em className={`ssl-status ${check.status}`}>{statusLabels[check.status]}</em>
                  </div>
                  <div className="ssl-metrics">
                    <div><span>Expiration</span><strong>{formatDate(check.expires_at)}</strong></div>
                    <div><span>Jours restants</span><strong>{check.days_remaining ?? "—"}</strong></div>
                    <div><span>Chaîne fiable</span><strong>{check.chain_valid ? "Oui" : "Non"}</strong></div>
                  </div>
                  <p>{check.issuer ? `Émetteur : ${check.issuer}` : check.error || "Informations indisponibles."}</p>
                  {(check.tls_version || check.cipher) && <small>{[check.tls_version, check.cipher].filter(Boolean).join(" · ")}</small>}
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
