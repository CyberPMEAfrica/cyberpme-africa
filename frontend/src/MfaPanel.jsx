import { useEffect, useState } from 'react';
import { apiFetch } from './api';
import MfaQrCode from './MfaQrCode';

export default function MfaPanel({ apiUrl, onReconnect }) {
  const [status, setStatus] = useState(null);
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [setup, setSetup] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { apiFetch(`${apiUrl}/api/v1/auth/mfa/status`).then(r => r.ok ? r.json() : Promise.reject()).then(setStatus).catch(() => setError('État MFA indisponible.')); }, [apiUrl]);
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/auth/mfa/${status?.enabled ? 'reset' : setup ? 'enable' : 'setup'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password, code }) });
      if (response.status === 204) { setPassword(''); setCode(''); setStatus({ ...status, enabled: false }); onReconnect(); return; }
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Opération impossible.');
      if (setup) { setRecovery(data.recovery_codes); setSetup(null); setPassword(''); setCode(''); }
      else setSetup(data);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <section className="settings-panel settings-form-narrow">
    <h3>Authentification à deux facteurs</h3>
    {recovery ? <><p>MFA activée. Vos sessions sont fermées. Conservez ces codes à usage unique dans un gestionnaire de mots de passe ; ils ne seront plus affichés.</p><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{recovery.join('\n')}</pre><button onClick={() => { setRecovery(null); onReconnect(); }}>Codes sauvegardés — me reconnecter</button></>
    : status?.enabled ? <><p>MFA activée · {status.recovery_codes_remaining} codes de secours restants.</p><details><summary>Remplacer mon application d’authentification</summary><p>Le mot de passe et un code actuel ou de secours sont nécessaires. Les autres sessions et les anciens codes seront invalidés. Une nouvelle configuration MFA sera obligatoire.</p><form onSubmit={submit}><label>Mot de passe actuel<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" minLength={12} required/></label><label>Code MFA ou de secours<input value={code} onChange={e => setCode(e.target.value)} autoComplete="one-time-code" maxLength={64} required/></label><button disabled={busy}>Réinitialiser et reconfigurer la MFA</button></form></details></>
    : <form onSubmit={submit}><p>Ajoutez CyberPME dans une application d’authentification compatible TOTP. Aucun code n’est envoyé par e-mail ou SMS.</p>
      <label>Mot de passe actuel<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" minLength={12} required/></label>
      {setup && <><MfaQrCode setup={setup}/><label>Clé à saisir dans l’application<input readOnly value={setup.secret}/></label><small>Nom : CyberPME · code à 6 chiffres · renouvellement toutes les 30 secondes. Ne partagez jamais cette clé.</small><label>Code actuel<input value={code} onChange={e => setCode(e.target.value)} inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" required/></label></>}
      <button disabled={busy || !status}>{busy ? 'Vérification…' : setup ? 'Activer et recevoir les codes de secours' : 'Préparer la MFA'}</button>
    </form>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
