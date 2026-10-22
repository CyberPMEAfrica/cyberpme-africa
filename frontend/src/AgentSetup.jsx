import { useState } from "react";
import { apiFetch as fetch } from './api';

export default function AgentSetup({ apiUrl, token, currentUser }) {
  const [installation, setInstallation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState('monitoring');
  const canInstall = ["owner", "admin"].includes(currentUser.role);
  const quote = (value) => `'${value.replaceAll("'", "''")}'`;
  const release = __AGENT_RELEASE_COMMIT__;
  const releaseReady = /^[a-f0-9]{40}$/i.test(release);
  const agentApi = import.meta.env.VITE_AGENT_API_URL || apiUrl;
  const command = installation ? `$p = Join-Path $env:TEMP 'install-cyberpme-agent.ps1'; Invoke-WebRequest -UseBasicParsing ${quote(`https://raw.githubusercontent.com/CyberPMEAfrica/cyberpme-africa/${release}/scripts/install-cyberpme-agent.ps1`)} -OutFile $p; & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -ApiUrl ${quote(agentApi)} -EnrollmentToken ${quote(installation.enrollment_token)} -Mode ${quote(installation.mode)} -SourceRevision ${quote(release)}` : "";
  async function generate() {
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/agent-enrollment-tokens`, { method: "POST", headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Impossible de préparer l’installation.");
      setInstallation(data);
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(command); setMessage("Commande copiée. Collez-la dans PowerShell ouvert en administrateur sur le PC à connecter."); }
    catch { setMessage("Sélectionnez et copiez la commande ci-dessus."); }
  }
  return <details className="agent-setup">
    <summary>Connecter un PC Windows</summary>
    <p>Installez un agent sur un PC du réseau à analyser. Ce PC doit rester allumé et connecté à Internet pendant les audits.</p>
    {canInstall ? <>
      <label>Permissions de l’agent<select value={mode} onChange={e => { setMode(e.target.value); setInstallation(null); }}><option value="monitoring">Monitoring seul — recommandé pour un VPS client</option><option value="network">Monitoring et audits réseau autorisés</option><option value="managed">Opérations administrées — configuration locale obligatoire</option></select></label>
      <p>En mode monitoring, aucun audit réseau ni commande de sauvegarde ou de pare-feu n’est exécuté.</p>
      <ol><li>Générez la commande d’installation.</li><li>Ouvrez PowerShell en administrateur sur le PC concerné et collez la commande.</li><li>Validez l’installation de Python, Nmap et Npcap si elle est proposée, puis actualisez cette page.</li></ol>
      {!releaseReady && <p>La révision de publication de l’agent doit être configurée avant de générer une commande d’installation.</p>}
      <button type="button" disabled={busy || !releaseReady} onClick={generate}>{busy ? "Préparation…" : "Générer la commande Windows"}</button>
      {installation && <>
        <p>Usage unique · valable jusqu’à {new Date(installation.expires_at).toLocaleTimeString("fr-FR")}. Gardez cette commande privée.</p>
        <textarea aria-label="Commande d’installation Windows" readOnly value={command} rows={6} />
        <button type="button" className="secondary-button" onClick={copy}>Copier la commande</button>
      </>}
    </> : <p>Demandez au propriétaire ou à un administrateur de connecter ce PC.</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}
