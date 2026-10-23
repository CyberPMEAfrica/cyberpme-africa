import React, { useEffect, useRef, useState } from "react";
import { API_URL, apiFetch as fetch } from './api';
import { LOGOUT_PENDING_KEY, revokeBrowserSession } from './logout-session';
import MfaPanel from './MfaPanel';
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./alerts.css";
import "./scanner.css";
import "./shell.css";
import "./theme.css";
import "./brand.css";
import AppShell, { activePages } from "./AppShell";
import NetworkScanner from "./NetworkScanner";
import BackupsPage from "./BackupsPage";
import ManagedActions from "./ManagedActions";
import InvitationPage from "./InvitationPage";
import LoginPage from "./LoginPage";
import ReportsPage from "./ReportsPage";
import SecurityEventsPage from "./SecurityEventsPage";
import SettingsPage from "./SettingsPage";
import SslMonitor from "./SslMonitor";
import InterfaceIcon from "./InterfaceIcon";
import OverviewDashboard from "./OverviewDashboard";
import "./experience.css";

const AUTO_REFRESH_MS = 10_000;
const labels = { unknown: "En attente", online: "Opérationnel", warning: "Attention", critical: "Critique" };

function Metric({ label, value }) {
  const percentage = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
  return <div className="metric"><span>{label}</span><strong>{percentage == null ? "—" : `${Math.round(percentage)} %`}</strong><div className={`metric-track ${percentage >= 90 ? 'metric-high' : percentage >= 75 ? 'metric-elevated' : ''}`} aria-hidden="true"><i style={{width: `${percentage ?? 0}%`}}/></div></div>;
}

function ServerCards({ servers, error, limit }) {
  const displayed = limit ? servers.slice(0, limit) : servers;
  if (!displayed.length && !error) {
    return <div className="empty"><h3>Aucun serveur enregistré</h3><p>Connectez votre premier PC avec l’agent CyberPME.</p><a href="#/scanner">Installer l’agent Windows</a></div>;
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
  const [sessionToken, setSessionToken] = useState(() => {
    localStorage.removeItem('cyberpme_session');
    return sessionStorage.getItem(LOGOUT_PENDING_KEY) ? '' : 'cookie';
  });
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
  const [logoutStatus, setLogoutStatus] = useState(() => sessionStorage.getItem(LOGOUT_PENDING_KEY) ? 'pending' : 'idle');
  const sessionEpoch = useRef(0);
  const syncRequests = useRef(new Set());
  const refreshInterval = useRef(null);
  const logoutRequest = useRef(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";
    localStorage.setItem("cyberpme_theme", theme);
  }, [theme]);

  async function loadData(token = sessionToken) {
    if (!token || sessionStorage.getItem(LOGOUT_PENDING_KEY)) return false;
    const epoch = sessionEpoch.current;
    const controller = new AbortController();
    syncRequests.current.add(controller);
    setIsRefreshing(true);
    try {
      const request = (path) => fetch(`${API_URL}${path}`, { signal: controller.signal });
      const [serverResponse, alertResponse, scanResponse, sslResponse, backupResponse, securityResponse, connectorResponse] = await Promise.all([
        request("/api/v1/servers"), request("/api/v1/alerts"), request("/api/v1/network-scans"),
        request("/api/v1/ssl-checks"), request("/api/v1/backup-checks"), request("/api/v1/security-events"),
        request("/api/v1/ids-connectors"),
      ]);
      if (!serverResponse.ok || !alertResponse.ok || !scanResponse.ok || !sslResponse.ok || !backupResponse.ok || !securityResponse.ok || !connectorResponse.ok) throw new Error();
      const data = await Promise.all([serverResponse, alertResponse, scanResponse, sslResponse, backupResponse, securityResponse, connectorResponse].map(response => response.json()));
      if (epoch !== sessionEpoch.current || controller.signal.aborted) return false;
      [setServers, setAlerts, setNetworkScans, setSslChecks, setBackupChecks, setSecurityEvents, setIdsConnectors].forEach((set, index) => set(data[index]));
      setError("");
      setLastUpdated(new Date());
      return true;
    } catch {
      if (epoch === sessionEpoch.current && !controller.signal.aborted) setError("La synchronisation a échoué. Vérifiez votre connexion, puis réessayez avec Actualiser.");
      return false;
    } finally {
      syncRequests.current.delete(controller);
      if (epoch === sessionEpoch.current) setIsRefreshing(false);
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
    const epoch = sessionEpoch.current;
    const controller = new AbortController();
    syncRequests.current.add(controller);
    const isCurrent = () => epoch === sessionEpoch.current && !controller.signal.aborted;
    fetch(`${API_URL}/api/v1/auth/me`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(user => {
        if (!isCurrent()) return;
        setCurrentUser(user);
        setTheme(user.theme || "dark");
        loadData(sessionToken);
      })
      .catch(() => { if (isCurrent()) clearLocalSession(); })
      .finally(() => syncRequests.current.delete(controller));
    const timer = setInterval(() => loadData(sessionToken), AUTO_REFRESH_MS);
    refreshInterval.current = timer;
    return () => { clearInterval(timer); controller.abort(); syncRequests.current.delete(controller); };
  }, [sessionToken]);

  useEffect(() => {
    if (sessionStorage.getItem(LOGOUT_PENDING_KEY)) logout();
  }, []);

  function authenticated(session) {
    sessionEpoch.current += 1;
    setLogoutStatus('idle');
    setSessionToken('cookie');
  }

  function clearLocalSession() {
    sessionEpoch.current += 1;
    clearInterval(refreshInterval.current);
    for (const controller of syncRequests.current) controller.abort();
    syncRequests.current.clear();
    localStorage.removeItem("cyberpme_session");
    setSessionToken("");
    setCurrentUser(null);
    [setServers, setAlerts, setNetworkScans, setSslChecks, setBackupChecks, setSecurityEvents, setIdsConnectors].forEach(set => set([]));
    setError('');
    setLastUpdated(null);
    setIsRefreshing(false);
  }

  function logout() {
    if (logoutRequest.current) return logoutRequest.current;
    sessionStorage.setItem(LOGOUT_PENDING_KEY, '1');
    clearLocalSession();
    setLogoutStatus('pending');
    logoutRequest.current = revokeBrowserSession(fetch, `${API_URL}/api/v1/auth/logout`)
      .then(() => { sessionStorage.removeItem(LOGOUT_PENDING_KEY); setLogoutStatus('done'); })
      .catch(() => setLogoutStatus('failed'))
      .finally(() => { logoutRequest.current = null; });
    return logoutRequest.current;
  }

  function passwordChanged() {
    clearLocalSession();
  }

  function themeChanged(user) {
    setCurrentUser(user);
    setTheme(user.theme);
  }

  const invitationToken = invitationTokenFromHash();
  if (invitationToken && logoutStatus !== 'pending' && logoutStatus !== 'failed') {
    return <InvitationPage apiUrl={API_URL} token={invitationToken} onAuthenticated={(session) => {
      authenticated(session);
      window.location.hash = "/overview";
    }}/>;
  }
  if (sessionToken && !currentUser) return <div className="session-loading" role="status"><InterfaceIcon name="refresh" className="is-spinning"/><p>Ouverture de votre espace…</p></div>;
  if (!sessionToken) return <LoginPage apiUrl={API_URL} onAuthenticated={authenticated} logoutStatus={logoutStatus} onRetryLogout={logout}/>;
  if (currentUser?.mfa_setup_required) return <main className="login-screen"><section className="login-card mfa-setup-card"><h1>Sécuriser votre compte</h1><p>L’authentification à deux facteurs est obligatoire avant d’accéder aux données.</p><MfaPanel apiUrl={API_URL} onReconnect={passwordChanged}/><button className="secondary-button" onClick={logout}>Se déconnecter</button></section></main>;

  let page;
  if (activePage === "servers") page = <ServersPage servers={servers} error={error}/>;
  else if (activePage === "alerts") page = <AlertsPage alerts={alerts}/>;
  else if (activePage === "scanner") page = <NetworkScanner apiUrl={API_URL} token={sessionToken} scans={networkScans} servers={servers} currentUser={currentUser} onCreated={loadData}/>;
  else if (activePage === "ssl") page = <SslMonitor apiUrl={API_URL} token={sessionToken} checks={sslChecks} currentUser={currentUser} onCreated={loadData}/>;
  else if (activePage === "reports") page = <ReportsPage apiUrl={API_URL} token={sessionToken} scans={networkScans}/>;
  else if (activePage === "backups") page = <><BackupsPage checks={backupChecks}/><ManagedActions mode="backup" apiUrl={API_URL} token={sessionToken} servers={servers} currentUser={currentUser}/></>;
  else if (activePage === "ids") page = <><SecurityEventsPage apiUrl={API_URL} token={sessionToken} events={securityEvents} connectors={idsConnectors} servers={servers} currentUser={currentUser} onCreated={loadData}/><ManagedActions mode="firewall" apiUrl={API_URL} token={sessionToken} servers={servers} currentUser={currentUser} events={securityEvents}/></>;
  else if (activePage === "settings") page = (
    <SettingsPage
      apiUrl={API_URL}
      token={sessionToken}
      currentUser={currentUser}
      onPasswordChanged={passwordChanged}
      onThemeChanged={themeChanged}
    />
  );
  else page = <OverviewDashboard servers={servers} alerts={alerts} networkScans={networkScans} sslChecks={sslChecks} backupChecks={backupChecks} securityEvents={securityEvents} lastUpdated={lastUpdated} error={error}/>;

  return <AppShell activePage={activePage} onNavigate={navigate} apiOnline={error ? false : lastUpdated ? true : null} isRefreshing={isRefreshing} lastUpdated={lastUpdated} refreshIntervalSeconds={AUTO_REFRESH_MS / 1000} onRefresh={() => loadData()} currentUser={currentUser} onLogout={logout}>
    {error && <p className="error">{error}</p>}
    {page}
  </AppShell>;
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App/></React.StrictMode>);
