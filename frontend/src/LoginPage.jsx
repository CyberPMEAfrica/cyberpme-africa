import { useState } from "react";
import BrandLogo from "./BrandLogo";
import InterfaceIcon from './InterfaceIcon';

export default function LoginPage({ apiUrl, onAuthenticated }) {
  const [organization, setOrganization] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_slug: organization, email, password }),
      });
      if (!response.ok) throw new Error(response.status === 401 || response.status === 422 ? 'Organisation, adresse e-mail ou mot de passe incorrect.' : 'Connexion momentanément indisponible. Réessayez dans un instant.');
      onAuthenticated(await response.json());
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
    <form onSubmit={submit}>
      <label>Organisation<input name="organization" value={organization} onChange={e => setOrganization(e.target.value)} placeholder="ex. mon-entreprise" autoComplete="organization" aria-describedby="organization-help" required/></label>
      <small id="organization-help" className="login-help">Utilisez l’identifiant fourni par votre administrateur.</small>
      <label>Adresse e-mail<input name="username" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="vous@entreprise.fr" autoComplete="username" required/></label>
      <div className="password-field"><label>Mot de passe<input name="password" type={passwordVisible ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" minLength="12" required/></label><button type="button" className="password-toggle" onClick={() => setPasswordVisible(!passwordVisible)} aria-label={passwordVisible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} aria-pressed={passwordVisible}><InterfaceIcon name="eye"/></button></div>
      {error && <p className="login-error" role="alert">{error}</p>}
      <button disabled={loading} aria-busy={loading}><InterfaceIcon name={loading ? 'refresh' : 'arrow'} className={loading ? 'is-spinning' : ''}/>{loading ? "Connexion…" : "Se connecter"}</button>
    </form>
  </section></main>;
}
