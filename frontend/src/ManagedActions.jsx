import { useCallback, useEffect, useState } from 'react';
import './managed-actions.css';

const labels = { proposed:'À approuver', approved:'Approuvée, en attente', running:'En cours', completed:'Exécutée', failed:'Échec', uncertain:'À vérifier localement', cancelled:'Annulée' };
const kinds = { backup:'Sauvegarde', restore_test:'Restauration de test', firewall_block:'Blocage temporaire', firewall_unblock:'Annulation du blocage' };

export default function ManagedActions({ apiUrl, token, servers, currentUser, events=[], mode }) {
  const [actions,setActions]=useState([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [server,setServer]=useState('');
  const [profile,setProfile]=useState('');
  const [eventId,setEventId]=useState('');
  const [reason,setReason]=useState('');
  const [minutes,setMinutes]=useState(15);
  const canPropose=['owner','admin','analyst'].includes(currentUser.role);
  const canApprove=['owner','admin'].includes(currentUser.role);
  const headers={Authorization:`Bearer ${token}`,'Content-Type':'application/json'};
  const reload=useCallback(async()=>{
    try {
      const response=await fetch(`${apiUrl}/api/v1/managed-actions`,{headers:{Authorization:`Bearer ${token}`}});
      if (!response.ok) throw new Error('Historique des actions indisponible. Vérifiez la version du serveur.');
      setActions(await response.json());
    } catch(e) { setError(e.message); }
  },[apiUrl,token]);
  useEffect(()=>{reload(); const timer=setInterval(reload,10000); return ()=>clearInterval(timer);},[reload]);
  async function send(path,payload,confirmation) {
    if (busy || (confirmation && !window.confirm(confirmation))) return;
    setBusy(true);setError('');
    try {
      const response=await fetch(`${apiUrl}/api/v1/managed-actions${path}`,{method:'POST',headers,body:payload?JSON.stringify(payload):undefined});
      const body=await response.json().catch(()=>({}));
      if (!response.ok) throw new Error(typeof body.detail==='string'?body.detail:'Demande refusée. Vérifiez les champs et vos droits.');
      await reload();
    } catch(e) {setError(e.message);} finally {setBusy(false);}
  }
  function propose(e) {
    e.preventDefault();
    if (mode==='backup') send('',{server_id:server,kind:'backup',profile,reason});
    else {
      const event=events.find(x=>x.id===eventId);
      if(event) send('',{server_id:event.server_id,kind:'firewall_block',event_id:event.id,duration_minutes:Number(minutes),reason});
    }
  }
  const visible=actions.filter(x=>mode==='backup'?['backup','restore_test'].includes(x.kind):x.kind.startsWith('firewall_'));
  return <section className="managed-actions">
    <h2>{mode==='backup'?'Sauvegardes actives et restauration de test':'Réponse aux incidents avec approbation'}</h2>
    <p>{mode==='backup'?'Agent 0.3 requis. Les profils et secrets se configurent localement. La restauration crée un nouveau dossier, sans écraser les données.':'Agent 0.3 et politique locale requis. Blocage TCP entrant d’une IPv4 publique sur le poste sélectionné, pendant 1 à 60 minutes. Les ports administratifs sont exclus. Aucun blocage automatique.'}</p>
    <p>Créer une proposition ne lance aucune opération. Un propriétaire ou administrateur doit ensuite l’approuver.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {canPropose && <form onSubmit={propose}>
      {mode==='backup'?<>
        <label>Machine<select required value={server} onChange={e=>setServer(e.target.value)}><option value="">Choisir un agent</option>{servers.map(s=><option key={s.id} value={s.id}>{s.name} · {s.hostname}</option>)}</select></label>
        <label>Profil local autorisé<input required pattern="[A-Za-z0-9_-]{1,64}" value={profile} onChange={e=>setProfile(e.target.value)} placeholder="Exemple : documents"/></label>
      </>:<>
        <label>Événement source<select required value={eventId} onChange={e=>setEventId(e.target.value)}><option value="">Choisir un événement</option>{events.filter(e=>e.source_ip).map(e=><option key={e.id} value={e.id}>{e.server_name} · {e.source_ip} · {e.title}</option>)}</select></label>
        <label>Durée maximale en minutes<input type="number" min="1" max="60" required value={minutes} onChange={e=>setMinutes(e.target.value)}/></label>
      </>}
      <label>Justification<textarea required minLength="10" maxLength="1000" value={reason} onChange={e=>setReason(e.target.value)}/></label>
      <button disabled={busy}>Proposer sans exécuter</button>
    </form>}
    <div className="managed-history">{visible.length===0?<p>Aucune action proposée.</p>:visible.map(a=><article key={a.id}>
      <h3>{kinds[a.kind]} · {servers.find(s=>s.id===a.server_id)?.name || a.server_id}</h3>
      <p><strong>{labels[a.status] || a.status}</strong> · {a.profile || a.source_ip} · {new Date(a.created_at).toLocaleString('fr-FR')}</p>
      <p>{a.reason}</p><p>Proposée par {a.proposed_by}{a.approved_by?` · Approuvée par ${a.approved_by}`:''}</p>
      {a.expires_at && <p>Échéance de l’autorisation : {new Date(a.expires_at).toLocaleString('fr-FR')}{a.kind==='firewall_block'?' — un statut exécuté décrit le résultat passé, pas une règle encore active.':''}</p>}
      {a.result?.message && <p>{a.result.message}</p>}
      {a.result?.snapshot && <p className="snapshot">Snapshot : {a.result.snapshot}</p>}
      <div className="managed-buttons">
        {canApprove && a.status==='proposed' && <button disabled={busy} onClick={()=>send(`/${a.id}/approve`,null,`Approuver ${kinds[a.kind]} sur cette machine ? La politique locale reste obligatoire.`)}>Approuver l’exécution</button>}
        {canApprove && (['proposed','approved'].includes(a.status) || (a.kind==='firewall_block' && ['running','completed','uncertain'].includes(a.status))) && <button disabled={busy} onClick={()=>send(`/${a.id}/cancel`,null,'Annuler la demande ou demander le retrait du blocage ? Le retrait distant exige un agent connecté.')}>Demander l’annulation</button>}
        {canPropose && a.kind==='backup' && a.status==='completed' && a.result?.snapshot && <button disabled={busy} onClick={()=>send('',{server_id:a.server_id,kind:'restore_test',profile:a.profile,snapshot:a.result.snapshot,reason:'Vérifier la restauration du snapshot '+a.result.snapshot},'Proposer une copie de restauration dans un nouveau dossier local ?')}>Proposer une restauration de test</button>}
      </div>
    </article>)}</div>
  </section>;
}
