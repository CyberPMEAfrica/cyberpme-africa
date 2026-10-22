import { useEffect, useRef, useState } from 'react';
import InterfaceIcon from './InterfaceIcon';
import { fleetStates, latestChecks, lastCompletedScan, openIncidents, resourceRows, severityLabels, stateLabels, timestamp } from './dashboard-data';
import './dashboard.css';

const resources = [
  { id: 'cpu_percent', label: 'CPU', color: 'mint' },
  { id: 'memory_percent', label: 'RAM', color: 'cyan' },
  { id: 'disk_percent', label: 'Disque', color: 'violet' },
];
const number = value => new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 0}).format(value);
const date = value => timestamp(value) ? new Date(value).toLocaleString('fr-FR', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : 'Date indisponible';
const percent = value => `${number(value)} %`;

function PanelHeading({ icon, title, note, children }) {
  return <div className="cc-panel-heading"><div><span className="cc-panel-icon"><InterfaceIcon name={icon}/></span><div><h3>{title}</h3>{note && <p>{note}</p>}</div></div>{children}</div>;
}

function Kpi({label, value, note, icon, tone, href, onClick}) {
  return <a className={`cc-kpi cc-${tone}`} href={href} onClick={onClick}><div><span>{label}</span><InterfaceIcon name={icon}/></div><strong>{value}</strong><small>{note}<InterfaceIcon name="arrow"/></small></a>;
}

function ResourcePanel({ servers, loaded }) {
  const [field, setField] = useState(resources[0].id);
  const selected = resources.find(item => item.id === field);
  const rows = resourceRows(servers, field);
  const average = rows.length ? rows.reduce((sum, row) => sum + row.value, 0) / rows.length : null;
  return <article className="cc-panel cc-resources">
    <PanelHeading icon="activity" title="Charge des ressources" note="Dernières mesures reçues"><span className={`cc-average cc-${selected.color}`}>{average == null ? '—' : percent(average)}<small>moyenne du parc</small></span></PanelHeading>
    <div className="cc-resource-tabs" role="group" aria-label="Ressource affichée">{resources.map(item => <button key={item.id} aria-pressed={field === item.id} onClick={() => setField(item.id)}>{item.label}</button>)}</div>
    <div className="cc-chart" aria-label={`Utilisation ${selected.label} par serveur`}>
      {rows.length ? <><div className="cc-chart-axis"><span>0</span><span>25</span><span>50</span><span>75</span><span>100 %</span></div>{rows.slice(0, 5).map(({server, value}) => <div className="cc-bar-row" key={server.id}><div><span title={server.name}>{server.name}</span><strong>{percent(value)}</strong></div><div className="cc-bar-track" aria-hidden="true"><i className={`cc-bar-fill cc-${value >= 90 ? 'red' : value >= 75 ? 'amber' : selected.color}`} style={{width:`${value}%`}}/></div></div>)}</> : <div className="cc-empty"><InterfaceIcon name="activity"/><p>{loaded ? 'Aucune mesure disponible' : 'Chargement des mesures…'}</p><small>Les graphiques apparaîtront avec les données des agents.</small></div>}
    </div>
    <footer className="cc-panel-footer"><span>{rows.length} / {servers.length} serveurs avec une mesure {selected.label}{rows.length > 5 ? ' · 5 plus chargés affichés' : ''}</span><a href="#/servers">Voir le parc<InterfaceIcon name="arrow"/></a></footer>
  </article>;
}

function HealthPanel({ servers, loaded }) {
  const counts = fleetStates(servers);
  const total = servers.length;
  let offset = 0;
  const segments = Object.entries(counts).map(([state, count]) => {
    const length = total ? count / total * 100 : 0;
    const segment = {state, count, length, offset}; offset += length; return segment;
  });
  return <article className="cc-panel cc-health">
    <PanelHeading icon="shield" title="État de l’infrastructure" note="Derniers états reçus · pas un taux de disponibilité historique"/>
    <div className="cc-health-body"><div className="cc-ring" role="img" aria-label={loaded ? `${counts.online} serveurs opérationnels sur ${total}` : 'État en cours de chargement'}><svg viewBox="0 0 160 160" aria-hidden="true"><circle className="cc-ring-track" cx="80" cy="80" r="62"/>{segments.filter(item=>item.count).map(item => <circle key={item.state} className={`cc-state-${item.state}`} cx="80" cy="80" r="62" pathLength="100" strokeDasharray={`${item.length} ${100-item.length}`} strokeDashoffset={-item.offset}/>)}</svg><div><strong>{total && loaded ? percent(counts.online / total * 100) : '—'}</strong><span>opérationnels</span></div></div>
      <div className="cc-state-legend">{segments.map(({state,count})=><div key={state}><i className={`cc-dot cc-state-${state}`}/><span>{stateLabels[state]}</span><strong>{loaded ? number(count) : '—'}</strong></div>)}</div>
    </div>
    <a className="cc-health-link" href="#/scanner"><InterfaceIcon name="network"/>Connecter un équipement<InterfaceIcon name="arrow"/></a>
  </article>;
}

function FleetPanel({servers, hosts, loaded}) {
  const [mode, setMode] = useState('monitored');
  const [query, setQuery] = useState('');
  const [attention, setAttention] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const needle = query.trim().toLocaleLowerCase('fr-FR');
  const items = mode === 'monitored' ? servers : hosts.map((host,index)=>({id:`discovered-${host.ip_address || index}`,name:host.hostname || host.ip_address || 'Équipement',hostname:host.hostname,ip_address:host.ip_address,status:'discovered',ports:Array.isArray(host.ports)?host.ports:[]}));
  const filtered = items.filter(server => (!attention || ['warning','critical'].includes(server.status)) && [server.name,server.hostname,server.ip_address].filter(Boolean).join(' ').toLocaleLowerCase('fr-FR').includes(needle));
  const selected = filtered.find(server => server.id === selectedId);
  return <article className="cc-panel cc-fleet">
    <PanelHeading icon="network" title="Carte des équipements" note={mode === 'monitored' ? 'Inventaire logique · aucune liaison réseau déduite' : 'Dernier audit terminé · santé des hôtes non évaluée'}><span className="cc-count">{filtered.length}</span></PanelHeading>
    <div className="cc-resource-tabs cc-inventory-tabs" role="group" aria-label="Équipements affichés">{[['monitored','Supervisés'],['discovered','Découverts']].map(([id,label])=><button key={id} aria-pressed={mode===id} onClick={()=>{setMode(id);setAttention(false);setSelectedId('');setQuery('');}}>{label} · {id==='monitored'?servers.length:hosts.length}</button>)}</div>
    <div className="cc-fleet-tools"><label className="cc-search"><InterfaceIcon name="search"/><input aria-label="Rechercher dans le parc" placeholder="Nom, adresse IP…" value={query} onChange={event=>setQuery(event.target.value)}/></label>{mode==='monitored' && <button className="cc-filter" aria-pressed={attention} onClick={()=>setAttention(!attention)}><InterfaceIcon name="filter"/>À surveiller</button>}</div>
    <div className="cc-equipment-grid">{filtered.slice(0, 24).map(server=>{
      const state = server.status==='discovered' ? 'discovered' : Object.hasOwn(stateLabels,server.status) ? server.status : 'unknown';
      const label = state==='discovered' ? 'Détecté' : stateLabels[state];
      return <button className={`cc-equipment cc-state-${state}`} key={server.id} aria-pressed={selectedId===server.id} onClick={()=>setSelectedId(selectedId===server.id?'':server.id)} title={`${server.name} · ${label}`}><span className="cc-node-icon"><InterfaceIcon name="servers"/><i className={`cc-dot cc-state-${state}`}/></span><strong>{server.name}</strong><small>{server.ip_address || server.hostname}</small><span className="cc-node-status">{label}</span></button>;
    })}</div>
    {!filtered.length && <div className="cc-empty"><p>{!loaded ? 'Chargement du parc…' : items.length ? 'Aucun équipement ne correspond' : mode==='discovered' ? 'Aucun équipement issu d’un audit' : 'Votre parc attend son premier équipement'}</p><small>{items.length ? 'Modifiez la recherche ou le filtre.' : mode==='discovered' ? 'Terminez un audit autorisé pour afficher ses résultats.' : 'Connectez un agent pour démarrer la supervision.'}</small></div>}
    {filtered.length > 24 && <p className="cc-footnote">24 équipements affichés sur {filtered.length}. Affinez la recherche ou ouvrez le parc complet.</p>}
    {selected && <div className="cc-equipment-details"><div><strong>{selected.name}</strong><span>{mode==='monitored' ? `Dernier contact : ${date(selected.last_seen_at)}` : `${selected.ports.length} port(s) ouvert(s) relevé(s)`}</span></div><div>{mode==='monitored' ? resources.map(item=><span key={item.id}>{item.label} <b>{Number.isFinite(selected.latest_metric?.[item.id]) ? percent(selected.latest_metric[item.id]) : '—'}</b></span>) : <span>{selected.ports.map(port=>`${port.port}/${port.protocol || 'tcp'}`).join(' · ') || 'Aucun port courant ouvert relevé.'}</span>}</div></div>}
    <footer className="cc-panel-footer"><span>{mode==='monitored' ? <><i className="cc-dot cc-state-online"/> Opérationnel <i className="cc-dot cc-state-warning"/> Attention <i className="cc-dot cc-state-critical"/> Critique</> : 'Résultats du dernier audit · pas une surveillance continue'}</span><a href={mode==='monitored'?'#/servers':'#/scanner'}>Tout voir<InterfaceIcon name="arrow"/></a></footer>
  </article>;
}

function IncidentsPanel({incidents, loaded}) {
  const counts = Object.keys(severityLabels).map(severity=>({severity,count:incidents.filter(item=>item.severity===severity).length}));
  return <article className="cc-panel cc-incidents">
    <PanelHeading icon="alerts" title="Priorités de sécurité" note="Alertes d’infrastructure et incidents IDS / IPS"><span className={`cc-count ${incidents.length ? 'cc-urgent' : ''}`}>{loaded ? incidents.length : '—'}</span></PanelHeading>
    <div className="cc-severity-summary">{counts.map(({severity,count})=><div className={`cc-severity-${severity}`} key={severity}><span>{severityLabels[severity]}</span><div aria-hidden="true"><i style={{width: `${incidents.length ? count/incidents.length*100 : 0}%`}}/></div><strong>{loaded ? count : '—'}</strong></div>)}</div>
    <div className="cc-incident-list">{incidents.slice(0,3).map(item=><a className={`cc-incident cc-severity-${item.severity}`} href={item.href} key={item.id}><div><span>{item.source}</span><time dateTime={item.date}>{date(item.date)}</time></div><strong>{item.title}</strong><small>{item.server || 'Organisation'}<InterfaceIcon name="arrow"/></small></a>)}</div>
    {!incidents.length && <div className="cc-empty"><InterfaceIcon name={loaded ? 'check' : 'clock'}/><p>{loaded ? 'Aucun incident ouvert remonté' : 'Chargement des incidents…'}</p><small>Cette vue reflète les alertes reçues par CyberPME.</small></div>}
    <footer className="cc-panel-footer"><a href="#/alerts">Infrastructure<InterfaceIcon name="arrow"/></a><a href="#/ids">Ouvrir IDS / IPS<InterfaceIcon name="arrow"/></a></footer>
  </article>;
}

function ContinuityPanel({certificates, backups, loaded}) {
  const certificatesOk = certificates.filter(item=>item.status==='valid').length;
  const backupsOk = backups.filter(item=>item.status==='healthy').length;
  return <article className="cc-panel cc-continuity">
    <PanelHeading icon="shield" title="Continuité & confiance" note="Dernier contrôle par domaine et par sauvegarde"/>
    <div className="cc-trust-grid">{[
      {href:'#/ssl',icon:'lock',name:'Certificats SSL',count:certificates.length,ok:certificatesOk,good:'valides',other:'à vérifier'},
      {href:'#/backups',icon:'backup',name:'Sauvegardes',count:backups.length,ok:backupsOk,good:'à jour',other:'à vérifier'},
    ].map(item=><a className="cc-trust-card" href={item.href} key={item.href}><span><InterfaceIcon name={item.icon}/>{item.name}<InterfaceIcon name="arrow"/></span><div><strong>{!loaded || !item.count ? '—' : `${item.ok}/${item.count}`}</strong><small>{item.good}</small></div><div className="cc-trust-track" aria-hidden="true"><i style={{width:`${item.count ? item.ok/item.count*100 : 0}%`}}/></div><p>{!loaded ? 'Chargement…' : item.count ? `${item.count-item.ok} ${item.other}` : 'Aucun contrôle reçu'}</p></a>)}</div>
  </article>;
}

export default function OverviewDashboard({servers, alerts, networkScans, sslChecks, backupChecks, securityEvents, lastUpdated, error}) {
  const root = useRef(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [screenError, setScreenError] = useState('');
  const loaded = Boolean(lastUpdated);
  const incidents = openIncidents(alerts, securityEvents);
  const certificates = latestChecks(sslChecks,item=>`${item.hostname.toLowerCase()}:${item.port}`);
  const backups = latestChecks(backupChecks,item=>`${item.server_id}:${item.name}`);
  const connected = servers.filter(item=>item.agent_connected).length;
  const scan = lastCompletedScan(networkScans);
  const hosts = Array.isArray(scan?.results) ? scan.results : [];
  const ports = hosts.reduce((sum,host)=>sum+(Array.isArray(host.ports)?host.ports.length:0),0);
  useEffect(()=>{const change=()=>setFullscreen(document.fullscreenElement===root.current); document.addEventListener('fullscreenchange',change); return ()=>document.removeEventListener('fullscreenchange',change);},[]);
  async function toggleFullscreen() {
    setScreenError('');
    try { if(document.fullscreenElement===root.current) await document.exitFullscreen(); else if(root.current?.requestFullscreen) await root.current.requestFullscreen(); else setScreenError('Le plein écran n’est pas disponible sur ce navigateur.'); }
    catch { setScreenError('Le navigateur n’a pas autorisé le mode plein écran.'); }
  }
  const count = value => loaded ? number(value) : '—';
  return <section className="command-center" ref={root} aria-label="Centre de supervision CyberPME">
    <div className="cc-toolbar"><div><p className="eyebrow">VISION GLOBALE</p><h2>Votre infrastructure.<span>Une longueur d’avance.</span></h2><p>Les signaux essentiels, les bonnes décisions.</p></div><div className="cc-toolbar-actions"><span className={`cc-live ${error ? 'cc-live-error' : ''}`}><i/>{error ? 'Données non actualisées' : loaded ? 'Supervision connectée' : 'Synchronisation…'}</span><button className="cc-fullscreen" onClick={toggleFullscreen} aria-pressed={fullscreen}><InterfaceIcon name={fullscreen?'minimize':'maximize'}/>{fullscreen?'Quitter le plein écran':'Plein écran'}</button></div></div>
    {screenError && <p className="cc-notice" role="status">{screenError}</p>}
    {fullscreen && <p className="cc-screen-sync">Actualisation automatique · 10 s · {error ? 'Synchronisation indisponible' : lastUpdated ? `Synchronisé à ${lastUpdated.toLocaleTimeString('fr-FR')}` : 'Chargement…'}</p>}
    <div className="cc-kpis" aria-label="Indicateurs clés">
      <Kpi label="Serveurs suivis" value={count(servers.length)} note={`${count(servers.filter(item=>item.status==='online').length)} opérationnels`} icon="servers" tone="mint" href="#/servers"/>
      <Kpi label="Agents connectés" value={count(connected)} note="Prêts pour les audits" icon="network" tone="cyan" href="#/scanner"/>
      <Kpi label="Alertes & incidents" value={count(incidents.length)} note="Non résolus" icon="alerts" tone={incidents.length?'red':'mint'} href="#cc-priorities" onClick={event=>{event.preventDefault();const panel=document.getElementById('cc-priorities');panel?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});panel?.focus({preventScroll:true});}}/>
      <Kpi label="Certificats suivis" value={count(certificates.length)} note="Domaines et ports TLS" icon="lock" tone="violet" href="#/ssl"/>
      <Kpi label="Sauvegardes suivies" value={count(backups.length)} note="Contrôles de continuité" icon="backup" tone="amber" href="#/backups"/>
      <Kpi label="Audits terminés" value={count(networkScans.filter(item=>item.status==='completed').length)} note="Rapports disponibles" icon="reports" tone="blue" href="#/reports"/>
    </div>
    <div className="cc-grid">
      <ResourcePanel servers={servers} loaded={loaded}/><HealthPanel servers={servers} loaded={loaded}/>
      <FleetPanel servers={servers} hosts={hosts} loaded={loaded}/><div className="cc-priorities" id="cc-priorities" tabIndex={-1} aria-label="Priorités de sécurité"><IncidentsPanel incidents={incidents} loaded={loaded}/></div>
      <ContinuityPanel certificates={certificates} backups={backups} loaded={loaded}/>
      <article className="cc-panel cc-scan"><PanelHeading icon="radar" title="Dernier audit réseau" note={scan ? date(scan.completed_at) : 'Dernier audit terminé disponible'}/>{scan ? <><div className="cc-scan-target"><span className="cc-radar" aria-hidden="true"><InterfaceIcon name="radar"/></span><div><small>RÉSEAU ANALYSÉ</small><strong>{scan.target}</strong><span>Analyse terminée</span></div></div><div className="cc-scan-stats"><div><strong>{hosts.length}</strong><span>équipements détectés</span></div><div><strong>{ports}</strong><span>ports ouverts relevés</span></div></div><a className="cc-scan-link" href="#/reports">Consulter les rapports<InterfaceIcon name="arrow"/></a></> : <div className="cc-empty"><InterfaceIcon name="radar"/><p>{loaded ? 'Aucun audit terminé' : 'Chargement des audits…'}</p><a href="#/scanner">Ouvrir le scanner<InterfaceIcon name="arrow"/></a></div>}</article>
    </div>
    <p className="cc-data-note"><InterfaceIcon name="clock"/>Données issues de l’API · les mesures absentes ne sont pas estimées.</p>
  </section>;
}
