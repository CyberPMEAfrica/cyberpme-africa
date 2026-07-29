import { useEffect, useState } from "react";

const roleLabels = {
  admin: "Administrateur",
  analyst: "Analyste",
  viewer: "Lecture seule",
};

async function responseError(response) {
  const body = await response.json().catch(() => ({}));
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((issue) => issue.msg || "Valeur invalide").join(" ");
  }
  return "Cette invitation ne peut pas être utilisée.";
}

export default function InvitationPage({ apiUrl, token, onAuthenticated }) {
  const [invitation, setInvitation] = useState(null);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${apiUrl}/api/v1/invitations/preview?token=${encodeURIComponent(token)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response));
        return response.json();
      })
      .then((data) => {
        setInvitation(data);
        setError("");
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [apiUrl, token]);

  async function accept(event) {
    event.preventDefault();
    if (password !== confirmation) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/invitations/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      onAuthenticated(await response.json());
    } catch (requestError) {
      setError(requestError.message);
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-card invitation-card">
        <div className="login-brand"><b>CA</b><div><strong>CyberPME</strong><small>AFRICA</small></div></div>
        <p className="eyebrow">INVITATION SÉCURISÉE</p>
        <h1>Rejoindre la PME</h1>
        {loading && !invitation && <p>Vérification du lien…</p>}
        {error && !invitation && (
          <>
            <p className="login-error">{error}</p>
            <a className="login-link" href="#/overview">Revenir à la connexion</a>
          </>
        )}
        {invitation && (
          <>
            <div className="invitation-summary">
              <span>Organisation</span><strong>{invitation.organization_name}</strong>
              <span>Adresse invitée</span><strong>{invitation.email}</strong>
              <span>Rôle</span><strong>{roleLabels[invitation.role]}</strong>
            </div>
            <form onSubmit={accept}>
              <label>Choisissez votre mot de passe
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength="12" autoComplete="new-password" required />
              </label>
              <label>Confirmez le mot de passe
                <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength="12" autoComplete="new-password" required />
              </label>
              <small>12 caractères minimum. Ce lien est personnel et utilisable une seule fois.</small>
              {error && <p className="login-error">{error}</p>}
              <button disabled={loading}>{loading ? "Activation…" : "Activer mon compte"}</button>
            </form>
          </>
        )}
      </section>
    </main>
  );
}
