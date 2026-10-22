import { useEffect, useState } from 'react';
import { apiFetch } from './api';

export default function AgentSecurity({ apiUrl, currentUser }) {
  const [agents, setAgents] = useState([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const allowed = ['owner', 'admin'].includes(currentUser.role);
  async function reload() {
    const response = await apiFetch(`${apiUrl}/api/v1/agent-security`);
    if (!response.ok) throw new Error('Liste des identités indisponible.');
    setAgents(await response.json());
  }
  useEffect(() => { if (allowed) reload().catch(e => setMessage(e.message)); }, [apiUrl, allowed]);
  async function revoke(agent) {
    if (!window.confirm(`Révoquer l’agent ${agent.name} ? Il ne pourra plus envoyer de mesures ni recevoir de tâches. Une nouvelle association sera nécessaire.`)) return;
    setBusy(true);
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/servers/${agent.server_id}/agent-credential/revoke`, { method: 'POST' });
      if (!response.ok) throw new Error('Révocation impossible.');
      await reload(); setMessage('Identité révoquée. Les données déjà collectées sont conservées.');
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  if (!allowed) return null;
  return <section className="settings-panel"><h3>Identités et permissions des agents</h3><p>Les jetons expirent au plus tard après 90 jours. La réassociation remplace le jeton précédent sans effacer les mesures.</p>
    {agents.map(agent => <article key={agent.server_id}><h4>{agent.name}</h4><p>{agent.hostname} · {agent.mode} · {agent.revoked_at ? 'Révoqué' : agent.expires_at ? `Expire le ${new Date(agent.expires_at).toLocaleDateString('fr-FR')}` : 'Non associé'}</p><button className="secondary-button" disabled={busy || !!agent.revoked_at || !agent.expires_at} onClick={() => revoke(agent)}>Révoquer l’accès</button></article>)}
    {message && <p role="status">{message}</p>}
  </section>;
}
