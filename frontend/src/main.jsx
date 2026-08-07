import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./alerts.css";
import "./scanner.css";
import "./shell.css";
import "./theme.css";
import AppShell, { activePages } from "./AppShell";
import NetworkScanner from "./NetworkScanner";
import BackupsPage from "./BackupsPage";
import InvitationPage from "./InvitationPage";
import LoginPage from "./LoginPage";
import ReportsPage from "./ReportsPage";
import SecurityEventsPage from "./SecurityEventsPage";
import SettingsPage from "./SettingsPage";
import SslMonitor from "./SslMonitor";

const API_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, "");
const labels = { unknown: "En attente", online: "Opérationnel", warning: "Attention", critical: "Critique" };

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value == null ? "—" : `${Math.round(value)} %`}</strong></div>;
}

function ServerCards({ servers, error, limit }) {
  const displayed = limit ? servers.slice(0, limit) : servers;
  if (!displayed.length && !error) {
    return <div className="empty"><h3>Aucun serveur enregistré</h3><p>Ajoutez le premier serveur depuis la documentation interactive.</p><a href={`${API_URL}/docs`}>Ouvrir l’API</a></div>;
  }
  return <div className="grid">{displayed.map((server) => (
    <article key={server.id}>
      <div className="server-head"><div><h3>{server.name}</h3><p>{server.hostname}{server.ip_address ? ` · ${server.ip_address}` : ""}</p></div><em className={`status ${server.status}`}>{labels[server.status]}</em></div>
      <div className="metrics"><Metric label="CPU" value={server.latest_metric?.cpu_percent}/><Metric label="RAM" value={server.latest_metric?.memory_percent}/><Metric label="Disque" value={server.latest_metric?.disk_percent}/></div>
    </article>
  ))}</div>;
}

function AlertCards({ alerts, limit }) {
  const displayed = limit ? alerts.slice(0, limit) : alerts;
  if (!displayed.length) {
    return <div className="all-clear"><span>✓</span><div><h3>Aucune alerte active</h3><p>Les ressources surveillées sont sous les seuils configurés.</p></div></div>;
  }
  return <div className="alert-list">{displayed.map((alert) => (
    <article className={`alert-card ${alert.severity}`} key={alert.id}>
      <div className="alert-top"><span>{alert.severity === "critical" ? "CRITIQUE" : "ATTENTION"}</span><small>{alert.server_name}</small></div>
      <h3>{alert.message}</h3><p>{alert.recommendation}</p>
    </article>
  ))}</div>;
}

function OverviewPage({ servers, alerts, error }) {
  const active = servers.filter((server) => server.status === "online").length;
  return <>
    <section className="overview-hero"><p className="eyebrow">CENTRE DE SUPERVISION</p><h2>Vos systèmes, sous contrôle.</h2><p>Une vue claire et immédiate de la santé de votre infrastructure.</p></section>
    <section className="summary overview-summary"><div><span>Serveurs suivis</span><strong>{servers.length}</strong></div><div><span>Opérationnels</span><strong className="green">{active}</strong></div><div><span>Alertes actives</span><strong className={alerts.length ? "red" : "green"}>{alerts.length}</strong></div></section>
    <div className="overview-columns">
      <section className="overview-block"><p className="eyebrow">INFRASTRUCTURE</p><h2>État récent</h2><ServerCards servers={servers} error={error} limit={3}/></section>
      <section className="overview-block"><p className="eyebrow">INCIDENTS</p><h2>Priorités</h2><AlertCards alerts={alerts} limit={3}/></section>
    </div>
  </>;
}

function ServersPage({ servers, error }) {
  return <section className="page-section"><div className="page-heading"><div><p className="eyebrow">INFRASTRUCTURE</p><h2>Serveurs supervisés</h2><p>État et ressources des agents CyberPME enregistrés.</p></div></div><ServerCards servers={servers} error={error}/></section>;
}

function AlertsPage({ alerts }) {
  return <section className="page-section"><div className="page-heading"><div><p className="eyebrow">INCIDENTS</p><h2>Alertes actives</h2><p>Incidents nécessitant une attention et recommandations associées.</p></div></div><AlertCards alerts={alerts}/></section>;
}

function pageFromHash() {
  const requested = window.location.hash.replace("#/", "");
  return activePages.includes(requested) ? requested : "overview";
}

function invitationTokenFromHash() {
  const hash = window.location.hash;
  if (!hash.startsWith("#/invite?")) return "";
  return new URLSearchParams(hash.split("?")[1] || "").get("token") || "";
}

function App() {
  const [sessionToken, setSessionToken] = useState(() => localStorage.getItem("cyberpme_session") || "");
  const [currentUser, setCurrentUser] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("cyberpme_theme") || "dark");
  const [activePage, setActivePage] = useState(pageFromHash);
  const [servers, setServers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [networkScans, setNetworkScans] = useState([]);
  const [sslChecks, setSslChecks] = useState([]);
  const [backupChecks, setBackupChecks] = useState([]);
  const [securityEvents, setSecurityEvents] = useState([]);
  const [idsConnectors, setIdsConnectors] = useState([]);
  const [error, setError] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";
    localStorage.setItem("cyberpme_theme", theme);
  }, [theme]);

  async function loadData(token = sessionToken) {
    if (!token) return;
    setIsRefreshing(true);
    try {
      const request = (path) => fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${token}` } });
      const [serverResponse, alertResponse, scanResponse, sslResponse, backupResponse, securityResponse, connectorResponse] = await Promise.all([
        request("/api/v1/servers"), request("/api/v1/alerts"), request("/api/v1/network-scans"),
        request("/api/v1/ssl-checks"), request("/api/v1/backup-checks"), request("/api/v1/security-events"),
        request("/api/v1/ids-connectors"),
      ]);
      if (!serverResponse.ok || !alertResponse.ok || !scanResponse.ok || !sslResponse.ok || !backupResponse.ok || !securityResponse.ok || !connectorResponse.ok) throw new Error();
      setServers(await serverResponse.json());
      setAlerts(await alertResponse.json());
      setNetworkScans(await scanResponse.json());
      setSslChecks(await sslResponse.json());
      setBackupChecks(await backupResponse.json());
      setSecurityEvents(await securityResponse.json());
      setIdsConnectors(await connectorResponse.json());
      setError("");
      setLastUpdated(new Date());
    } catch {
      setError("Impossible de joindre l’API. Vérifiez Docker.");
    } finally {
      setIsRefreshing(false);
    }
  }

  function navigate(page) {
    window.location.hash = `/${page}`;
  }

  useEffect(() => {
    const handleHash = () => setActivePage(pageFromHash());
    window.addEventListener("hashchange", handleHash);
    if (!window.location.hash) window.history.replaceState(null, "", "#/overview");
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  useEffect(() => {
    if (!sessionToken) { setCurrentUser(null); return; }
    fetch(`${API_URL}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${sessionToken}` } })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(user => {
        setCurrentUser(user);
        setTheme(user.theme || "dark");
        loadData(sessionToken);
      })
      .catch(() => { localStorage.removeItem("cyberpme_session"); setSessionToken(""); setCurrentUser(null); });
    const timer = setInterval(() => loadData(sessionToken), 10000);
    return () => clearInterval(timer);
  }, [sessionToken]);

  function authenticated(session) {
    localStorage.setItem("cyberpme_session", session.access_token);
    setSessionToken(session.access_token);
  }

  async function logout() {
    if (sessionToken) await fetch(`${API_URL}/api/v1/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${sessionToken}` } });
    localStorage.removeItem("cyberpme_session");
    setSessionToken("");
    setCurrentUser(null);
  }

  function passwordChanged() {
    localStorage.removeItem("cyberpme_session");
    setSessionToken("");
    setCurrentUser(null);
  }

  function themeChanged(user) {
    setCurrentUser(user);
    setTheme(user.theme);
  }

  const invitationToken = invitationTokenFromHash();
  if (invitationToken) {
    return <InvitationPage apiUrl={API_URL} token={invitationToken} onAuthenticated={(session) => {
      authenticated(session);
      window.location.hash = "/overview";
    }}/>;
  }
  if (!sessionToken || !currentUser) return <LoginPage apiUrl={API_URL} onAuthenticated={authenticated}/>;

  let page;
  if (activePage === "servers") page = <ServersPage servers={servers} error={error}/>;
  else if (activePage === "alerts") page = <AlertsPage alerts={alerts}/>;
  else if (activePage === "scanner") page = <NetworkScanner apiUrl={API_URL} token={sessionToken} scans={networkScans} onCreated={loadData}/>;
  else if (activePage === "ssl") page = <SslMonitor apiUrl={API_URL} token={sessionToken} checks={sslChecks} onCreated={loadData}/>;
  else if (activePage === "reports") page = <ReportsPage apiUrl={API_URL} token={sessionToken} scans={networkScans}/>;
  else if (activePage === "backups") page = <BackupsPage checks={backupChecks}/>;
  else if (activePage === "ids") page = <SecurityEventsPage apiUrl={API_URL} token={sessionToken} events={securityEvents} connectors={idsConnectors} servers={servers} currentUser={currentUser} onCreated={loadData}/>;
  else if (activePage === "settings") page = (
    <SettingsPage
      apiUrl={API_URL}
      token={sessionToken}
      currentUser={currentUser}
      onPasswordChanged={passwordChanged}
      onThemeChanged={themeChanged}
    />
  );
  else page = <OverviewPage servers={servers} alerts={alerts} error={error}/>;

  return <AppShell activePage={activePage} onNavigate={navigate} apiOnline={!error} isRefreshing={isRefreshing} lastUpdated={lastUpdated} onRefresh={() => loadData()} currentUser={currentUser} onLogout={logout}>
    {error && <p className="error">{error}</p>}
    {page}
  </AppShell>;
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App/></React.StrictMode>);
