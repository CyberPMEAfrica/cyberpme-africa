import { useState } from "react";
import { apiFetch as fetch } from './api';
import BrandLogo from "./BrandLogo";
import InterfaceIcon from './InterfaceIcon';

export default function LoginPage({ apiUrl, onAuthenticated, logoutStatus = 'idle', onRetryLogout }) {
  const [organization, setOrganization] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState('');
  const logoutUnconfirmed = logoutStatus === 'pending' || logoutStatus === 'failed';

  async function submit(event) {
    event.preventDefault();
    if (logoutUnconfirmed) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_slug: organization, email, password, mfa_code: mfaCode }),
      });
      const result = await response.json();
      if (result.detail === 'MFA_REQUIRED') { setMfaRequired(true); return; }
      if (!response.ok) throw new Error(response.status === 429 ? 'Trop de tentatives. Attendez 15 minutes avant de réessayer.' : mfaRequired ? 'Code MFA invalide, expiré ou déjà utilisé.' : 'Organisation, adresse e-mail ou mot de passe incorrect.');
      onAuthenticated(result);
    } catch (error) {
      setError(error instanceof TypeError ? 'Le service est injoignable. Vérifiez votre connexion, puis réessayez.' : error.message);
    } finally {
      setLoading(false);
    }
  }

  return <main className="login-screen"><section className="login-card">
    <div className="login-brand"><BrandLogo /></div>
    <p className="eyebrow">ESPACE SÉCURISÉ</p><h1>Connexion</h1>
    <p>Retrouvez votre infrastructure et vos priorités dans un espace dédié.</p>
    {logoutStatus === 'pending' && <p role="status">Espace fermé. Confirmation de la déconnexion en cours…</p>}
    {logoutStatus === 'done' && <p role="status">Vous êtes déconnecté.</p>}
    {logoutStatus === 'failed' && <div role="alert"><p className="login-error">Espace fermé sur cet onglet, mais la déconnexion côté serveur n’a pas pu être confirmée. Vérifiez votre connexion et réessayez avant de quitter un ordinateur partagé.</p><button type="button" className="secondary-button" onClick={onRetryLogout}>Réessayer la déconnexion</button></div>}
    <form onSubmit={submit}>
      <label>Organisation<input name="organization" value={organization} onChange={e => setOrganization(e.target.value)} placeholder="ex. mon-entreprise" autoComplete="organization" aria-describedby="organization-help" required/></label>
      <small id="organization-help" className="login-help">Utilisez l’identifiant fourni par votre administrateur.</small>
      <label>Adresse e-mail<input name="username" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="vous@entreprise.fr" autoComplete="username" required/></label>
      <div className="password-field"><label>Mot de passe<input name="password" type={passwordVisible ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" minLength="12" required/></label><button type="button" className="password-toggle" onClick={() => setPasswordVisible(!passwordVisible)} aria-label={passwordVisible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} aria-pressed={passwordVisible}><InterfaceIcon name="eye"/></button></div>
      {mfaRequired && <><label>Code de l’application d’authentification ou code de secours<input value={mfaCode} onChange={e => setMfaCode(e.target.value)} autoComplete="one-time-code" aria-describedby="mfa-help" maxLength={64} autoFocus required/></label><small id="mfa-help">Un code déjà utilisé ne peut pas être réutilisé. Attendez le prochain code si nécessaire.</small></>}
      {error && <p className="login-error" role="alert">{error}</p>}
      <button disabled={loading || logoutUnconfirmed} aria-busy={loading}><InterfaceIcon name={loading ? 'refresh' : 'arrow'} className={loading ? 'is-spinning' : ''}/>{loading ? "Connexion…" : "Se connecter"}</button>
    </form>
  </section></main>;
}
