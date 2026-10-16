import { useEffect, useRef, useState } from "react";
import BrandLogo from "./BrandLogo";
import InterfaceIcon from "./InterfaceIcon";

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
  { id: "backups", label: "Sauvegardes" },
  { id: "ids", label: "IDS / IPS" },
  { id: "settings", label: "Paramètres" },
];

function NavIcon({ name }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[name]}</svg>;
}

export const pageNames = Object.fromEntries(navigation.map((item) => [item.id, item.label]));
export const activePages = navigation.filter((item) => !item.upcoming).map((item) => item.id);

export default function AppShell({ activePage, onNavigate, apiOnline, isRefreshing, lastUpdated, onRefresh, currentUser, onLogout, children }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 780px)').matches);
  const [refreshed, setRefreshed] = useState(false);
  const accountRef = useRef(null);
  const avatarRef = useRef(null);
  const sidebarRef = useRef(null);
  const menuTriggerRef = useRef(null);
  const refreshTimer = useRef(null);
  const isLocalEnvironment = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const roleLabels = { owner: 'Propriétaire', admin: 'Administrateur', analyst: 'Analyste', viewer: 'Lecteur' };
  const email = currentUser?.email || '';

  useEffect(() => {
    const query = window.matchMedia('(max-width: 780px)');
    const update = () => { setIsMobile(query.matches); if (!query.matches) setMobileOpen(false); };
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!accountOpen) return;
    accountRef.current?.querySelector('[role="menuitem"]')?.focus();
    const outside = (event) => { if (!accountRef.current?.contains(event.target)) setAccountOpen(false); };
    const escape = (event) => { if (event.key === 'Escape') { setAccountOpen(false); avatarRef.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [accountOpen]);

  useEffect(() => {
    if (!mobileOpen) return;
    setAccountOpen(false);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    sidebarRef.current?.querySelector('button')?.focus();
    const keydown = (event) => {
      if (event.key === 'Escape') { setMobileOpen(false); return; }
      if (event.key !== 'Tab') return;
      const buttons = [...sidebarRef.current.querySelectorAll('button')].filter(el => el.getClientRects().length);
      const first = buttons[0], last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', keydown); menuTriggerRef.current?.focus(); };
  }, [mobileOpen]);

  useEffect(() => () => clearTimeout(refreshTimer.current), []);

  function accountKeyboard(event) {
    const items = [...accountRef.current.querySelectorAll('[role="menuitem"]')];
    const index = items.indexOf(document.activeElement);
    const next = event.key === 'ArrowDown' ? (index + 1) % items.length : event.key === 'ArrowUp' ? (index - 1 + items.length) % items.length : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : null;
    if (next !== null) { event.preventDefault(); items[next]?.focus(); }
    if (event.key === 'Tab') setAccountOpen(false);
  }

  async function refresh() {
    if (isRefreshing) return;
    setRefreshed(false);
    const success = await onRefresh();
    if (success) {
      setRefreshed(true);
      clearTimeout(refreshTimer.current);
      refreshTimer.current = setTimeout(() => setRefreshed(false), 2500);
    }
  }

  function navigate(page) {
    onNavigate(page);
    setMobileOpen(false);
    setAccountOpen(false);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Aller au contenu</a>
      {mobileOpen && <button className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-label="Fermer le menu" />}
      <aside id="main-sidebar" ref={sidebarRef} className={`sidebar ${mobileOpen ? "open" : ""}`} inert={isMobile && !mobileOpen} aria-label="Menu CyberPME">
        <button className="sidebar-close" onClick={() => setMobileOpen(false)} aria-label="Fermer la navigation"><InterfaceIcon name="close"/></button>
        <div className="sidebar-brand"><BrandLogo compact /></div>
        <nav aria-label="Navigation principale">
          <p>SUPERVISION</p>
          {navigation.slice(0, 8).map((item) => (
            <button key={item.id} aria-current={activePage === item.id ? 'page' : undefined} className={activePage === item.id ? "active" : ""} onClick={() => navigate(item.id)}>
              <NavIcon name={item.id}/><span>{item.label}</span>
            </button>
          ))}
          <p>COMPTE</p>
          <button aria-current={activePage === 'settings' ? 'page' : undefined} className={activePage === "settings" ? "active" : ""} onClick={() => navigate("settings")}>
            <NavIcon name="settings"/><span>Paramètres</span>
          </button>
        </nav>
        <div className="sidebar-footer"><InterfaceIcon name="shield"/><div><strong>{currentUser?.organization_name || 'CyberPME Africa'}</strong><small>{isLocalEnvironment ? "Espace de développement" : "Espace de démonstration"}</small></div></div>
      </aside>

      <div className="app-workspace" inert={isMobile && mobileOpen}>
        <header className="topbar">
          <div className="topbar-title"><button ref={menuTriggerRef} className="mobile-menu" onClick={() => setMobileOpen(true)} aria-controls="main-sidebar" aria-expanded={mobileOpen} aria-label="Ouvrir la navigation"><InterfaceIcon name="menu"/></button><div><p>ESPACE DE SUPERVISION</p><h1>{pageNames[activePage]}</h1></div></div>
          <div className="topbar-actions">
            <span className={`api-health ${apiOnline === false ? 'offline' : apiOnline ? 'online' : 'pending'}`} title={lastUpdated ? `Dernière synchronisation : ${lastUpdated.toLocaleTimeString('fr-FR')}` : 'En attente de synchronisation'}><i/>{apiOnline === false ? 'Connexion interrompue' : apiOnline ? 'API connectée' : 'Connexion…'}</span>
            <button className={`refresh-button ${refreshed ? 'is-done' : ''}`} onClick={refresh} disabled={isRefreshing} aria-busy={isRefreshing} aria-label={isRefreshing ? 'Actualisation en cours' : 'Actualiser les données'}><InterfaceIcon name={refreshed ? 'check' : 'refresh'} className={isRefreshing ? 'is-spinning' : ''}/><span>{isRefreshing ? "Actualisation…" : refreshed ? 'À jour' : 'Actualiser'}</span></button>
            <div className="account-control" ref={accountRef}>
              <button ref={avatarRef} className="account-trigger" onClick={() => setAccountOpen(!accountOpen)} aria-haspopup="menu" aria-expanded={accountOpen} aria-controls="account-menu" aria-label="Ouvrir le menu du compte">
                <span className="user-avatar">{email.slice(0, 2).toUpperCase() || 'CP'}</span><InterfaceIcon name="chevron"/>
              </button>
              {accountOpen && <div id="account-menu" className="account-menu" role="menu" aria-label="Mon compte" onKeyDown={accountKeyboard}>
                <div className="account-identity" role="presentation"><span className="account-label">MON ESPACE</span><strong>{email}</strong><span>{roleLabels[currentUser?.role] || 'Membre'} · {currentUser?.organization_name || 'CyberPME'}</span></div>
                <button role="menuitem" onClick={() => navigate('settings')}><InterfaceIcon name="account"/>Mon compte et paramètres<InterfaceIcon name="arrow"/></button>
                <button role="menuitem" className="account-logout" onClick={() => { setAccountOpen(false); onLogout(); }}><InterfaceIcon name="logout"/>Se déconnecter</button>
              </div>}
            </div>
          </div>
        </header>
        <span className="sr-only" role="status">{refreshed ? 'Données actualisées.' : ''}</span>
        <div className={`update-line ${apiOnline === false ? 'sync-error' : ''}`} aria-live="off">
          <InterfaceIcon name={apiOnline === false ? 'alerts' : 'clock'}/>{apiOnline === false ? 'Synchronisation indisponible · réessayez dans un instant' : lastUpdated ? `Synchronisé à ${lastUpdated.toLocaleTimeString("fr-FR")}` : "Première synchronisation…"}
        </div>
        <main id="main-content" tabIndex={-1} className="page-content"><div key={activePage} className="page-transition">{children}</div></main>
      </div>
    </div>
  );
}
