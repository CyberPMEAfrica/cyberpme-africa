import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./alerts.css";
import "./scanner.css";
import NetworkScanner from "./NetworkScanner";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const labels = { unknown: "En attente", online: "Opérationnel", warning: "Attention", critical: "Critique" };

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value == null ? "—" : `${Math.round(value)} %`}</strong></div>;
}

function App() {
  const [servers, setServers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [networkScans, setNetworkScans] = useState([]);
  const [error, setError] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  async function loadData() {
    setIsRefreshing(true);
    try {
      const [serverResponse, alertResponse, scanResponse] = await Promise.all([
        fetch(`${API_URL}/api/v1/servers`),
        fetch(`${API_URL}/api/v1/alerts`),
        fetch(`${API_URL}/api/v1/network-scans`),
      ]);
      if (!serverResponse.ok || !alertResponse.ok || !scanResponse.ok) throw new Error();
      setServers(await serverResponse.json());
      setAlerts(await alertResponse.json());
      setNetworkScans(await scanResponse.json());
      setError("");
      setLastUpdated(new Date());
    } catch { setError("Impossible de joindre l’API. Vérifiez Docker."); }
    finally { setIsRefreshing(false); }
  }
  useEffect(() => { loadData(); const timer = setInterval(loadData, 10000); return () => clearInterval(timer); }, []);
  const active = servers.filter((server) => server.status === "online").length;
  return <main>
    <header><div className="brand"><b>CA</b><div><strong>CyberPME</strong><small>AFRICA</small></div></div><button onClick={loadData} disabled={isRefreshing} aria-busy={isRefreshing}>{isRefreshing ? "Actualisation..." : "Actualiser"}</button></header>
    <section className="hero"><p className="eyebrow">CENTRE DE SUPERVISION</p><h1>Vos systèmes, sous contrôle.</h1><p>Une vue claire et immédiate de la santé de votre infrastructure.</p></section>
    <section className="summary"><div><span>Serveurs suivis</span><strong>{servers.length}</strong></div><div><span>Opérationnels</span><strong className="green">{active}</strong></div><div><span>Alertes actives</span><strong className={alerts.length ? "red" : "green"}>{alerts.length}</strong></div></section>
    {error && <p className="error">{error}</p>}
    <section className="servers"><div className="title"><div><p className="eyebrow">INFRASTRUCTURE</p><h2>Serveurs</h2></div><small aria-live="polite">{lastUpdated ? `Dernière mise à jour à ${lastUpdated.toLocaleTimeString("fr-FR")}` : "Chargement des données..."}</small></div>
      {!servers.length && !error ? <div className="empty"><h3>Aucun serveur enregistré</h3><p>Ajoutez le premier serveur depuis la documentation interactive.</p><a href={`${API_URL}/docs`}>Ouvrir l’API</a></div> : <div className="grid">{servers.map((server) => <article key={server.id}><div className="server-head"><div><h3>{server.name}</h3><p>{server.hostname}{server.ip_address ? ` · ${server.ip_address}` : ""}</p></div><em className={`status ${server.status}`}>{labels[server.status]}</em></div><div className="metrics"><Metric label="CPU" value={server.latest_metric?.cpu_percent}/><Metric label="RAM" value={server.latest_metric?.memory_percent}/><Metric label="Disque" value={server.latest_metric?.disk_percent}/></div></article>)}</div>}
    </section>
    <section className="alerts"><div className="title"><div><p className="eyebrow">INCIDENTS</p><h2>Alertes actives</h2></div></div>
      {!alerts.length ? <div className="all-clear"><span>✓</span><div><h3>Aucune alerte active</h3><p>Les ressources surveillées sont sous les seuils configurés.</p></div></div> : <div className="alert-list">{alerts.map((alert) => <article className={`alert-card ${alert.severity}`} key={alert.id}><div className="alert-top"><span>{alert.severity === "critical" ? "CRITIQUE" : "ATTENTION"}</span><small>{alert.server_name}</small></div><h3>{alert.message}</h3><p>{alert.recommendation}</p></article>)}</div>}
    </section>
    <NetworkScanner apiUrl={API_URL} scans={networkScans} onCreated={loadData} />
  </main>;
}
createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
