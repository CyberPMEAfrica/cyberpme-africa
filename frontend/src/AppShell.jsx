import { useState } from "react";

const icons = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  servers: <><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/></>,
  alerts: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
  scanner: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="M12 3v3M21 12h-3M12 21v-3M3 12h3"/></>,
  ssl: <><path d="M12 3 4 6v5c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></>,
  reports: <><path d="M6 2h9l4 4v16H6z"/><path d="M14 2v5h5M9 13h6M9 17h6"/></>,
  backups: <><path d="M5 19h14a3 3 0 0 0 0-6h-.3A7 7 0 0 0 5.4 10 4.5 4.5 0 0 0 5 19Z"/><path d="m9 14 3 3 3-3M12 17V9"/></>,
  ids: <><path d="M12 3 4 6v5c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V6l-8-3Z"/><path d="M12 8v5M12 17h.01"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
};

const navigation = [
  { id: "overview", label: "Vue d’ensemble" },
  { id: "servers", label: "Serveurs" },
  { id: "alerts", label: "Alertes" },
  { id: "scanner", label: "Scanner réseau" },
  { id: "ssl", label: "Certificats SSL" },
  { id: "reports", label: "Rapports" },
  { id: "backups", label: "Sauvegardes", upcoming: true },
  { id: "ids", label: "IDS / IPS", upcoming: true },
  { id: "settings", label: "Paramètres" },
];

function NavIcon({ name }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[name]}</svg>;
}

export const pageNames = Object.fromEntries(navigation.map((item) => [item.id, item.label]));
export const activePages = navigation.filter((item) => !item.upcoming).map((item) => item.id);

export default function AppShell({ activePage, onNavigate, apiOnline, isRefreshing, lastUpdated, onRefresh, children }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  function navigate(page) {
    onNavigate(page);
    setMobileOpen(false);
  }

  return (
    <div className="app-shell">
      <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Ouvrir le menu">☰</button>
      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Fermer le menu" />}
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <div className="sidebar-brand"><b>CA</b><div><strong>CyberPME</strong><small>AFRICA</small></div></div>
        <nav aria-label="Navigation principale">
          <p>SUPERVISION</p>
          {navigation.slice(0, 6).map((item) => (
            <button key={item.id} className={activePage === item.id ? "active" : ""} onClick={() => navigate(item.id)}>
              <NavIcon name={item.id}/><span>{item.label}</span>
            </button>
          ))}
          <p>PROCHAINEMENT</p>
          {navigation.slice(6, 8).map((item) => (
            <button key={item.id} disabled><NavIcon name={item.id}/><span>{item.label}</span><em>Bientôt</em></button>
          ))}
          <p>COMPTE</p>
          <button className={activePage === "settings" ? "active" : ""} onClick={() => navigate("settings")}>
            <NavIcon name="settings"/><span>Paramètres</span>
          </button>
        </nav>
        <div className="sidebar-footer"><span className="api-dot online"/><div><strong>CyberPME Local</strong><small>Environnement de développement</small></div></div>
      </aside>

      <div className="app-workspace">
        <header className="topbar">
          <div><p>CYBERPME AFRICA</p><h1>{pageNames[activePage]}</h1></div>
          <div className="topbar-actions">
            <span className={`api-health ${apiOnline ? "online" : "offline"}`}><i/>{apiOnline ? "API connectée" : "API indisponible"}</span>
            <button onClick={onRefresh} disabled={isRefreshing}>{isRefreshing ? "Actualisation..." : "Actualiser"}</button>
            <div className="user-avatar" title="CyberPME Africa">CP</div>
          </div>
        </header>
        <div className="update-line" aria-live="polite">
          {lastUpdated ? `Dernière synchronisation à ${lastUpdated.toLocaleTimeString("fr-FR")}` : "Chargement des données..."}
        </div>
        <main className="page-content">{children}</main>
      </div>
    </div>
  );
}
