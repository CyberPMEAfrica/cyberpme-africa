import { useState } from "react";

export default function LoginPage({ apiUrl, onAuthenticated }) {
  const [organization, setOrganization] = useState("cyberpme-lab");
  const [email, setEmail] = useState("bocorodrigue43@mail.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_slug: organization, email, password }),
      });
      if (!response.ok) throw new Error();
      onAuthenticated(await response.json());
    } catch {
      setError("Organisation, adresse e-mail ou mot de passe incorrect.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="login-screen"><section className="login-card">
    <div className="login-brand"><b>CA</b><div><strong>CyberPME</strong><small>AFRICA</small></div></div>
    <p className="eyebrow">ESPACE SÉCURISÉ</p><h1>Connexion</h1>
    <p>Accédez uniquement aux systèmes de votre organisation.</p>
    <form onSubmit={submit}>
      <label>Organisation<input value={organization} onChange={e => setOrganization(e.target.value)} required/></label>
      <label>Adresse e-mail<input type="email" value={email} onChange={e => setEmail(e.target.value)} required/></label>
      <label>Mot de passe<input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength="12" required/></label>
      {error && <p className="login-error">{error}</p>}
      <button disabled={loading}>{loading ? "Connexion..." : "Se connecter"}</button>
    </form>
  </section></main>;
}
