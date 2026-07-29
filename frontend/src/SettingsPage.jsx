import { useEffect, useState } from "react";

const roleLabels = {
  owner: "Propriétaire",
  admin: "Administrateur",
  analyst: "Analyste",
  viewer: "Lecture seule",
};

const auditActionLabels = {
  "auth.login": "Connexion réussie",
  "auth.logout": "Déconnexion",
  "auth.password_changed": "Mot de passe modifié",
  "organization.renamed": "Organisation renommée",
  "user.created": "Compte créé",
  "user.updated": "Compte modifié",
  "user.theme_changed": "Thème d’interface modifié",
  "invitation.created": "Invitation envoyée",
  "invitation.accepted": "Invitation acceptée",
  "security_incident.status_changed": "Incident mis à jour",
  "ids_connector.created": "Connecteur IDS créé",
  "ids_connector.revoked": "Connecteur IDS révoqué",
  "ids_connector.token_rotated": "Jeton IDS renouvelé",
  "ids_connector.previous_token_revoked": "Ancien jeton IDS révoqué",
};

const themeOptions = [
  {
    id: "light",
    name: "Clair",
    description: "Fond lumineux et contraste doux pour le travail en journée.",
  },
  {
    id: "dark",
    name: "Sombre bleu nuit",
    description: "Le thème CyberPME actuel, confortable et professionnel.",
  },
  {
    id: "black",
    name: "Noir profond",
    description: "Contraste renforcé et surfaces presque noires.",
  },
];

function auditTarget(entry) {
  const details = entry.details || {};
  if (details.email) return details.email;
  if (details.name) return details.name;
  if (details.new_name) return details.new_name;
  if (details.theme) return themeOptions.find((option) => option.id === details.theme)?.name || details.theme;
  if (details.rule_id) return `Règle ${details.rule_id}`;
  return entry.target_type;
}

const fieldLabels = {
  email: "Adresse e-mail",
  password: "Mot de passe initial",
  role: "Rôle",
  name: "Nom de la PME",
  theme: "Thème",
  current_password: "Mot de passe actuel",
  new_password: "Nouveau mot de passe",
};

function validationMessage(issue) {
  const field = issue?.loc?.at?.(-1);
  const label = fieldLabels[field] || "Champ";
  if (issue?.type === "string_too_short") {
    return `${label} : ${issue.ctx?.min_length || 12} caractères minimum.`;
  }
  if (issue?.type === "string_pattern_mismatch") {
    return `${label} : format invalide.`;
  }
  return `${label} : ${issue?.msg || "valeur invalide"}.`;
}

function apiErrorMessage(body) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) return body.detail.map(validationMessage).join(" ");
  if (body?.detail && typeof body.detail === "object") {
    return body.detail.message || "Les informations saisies ne sont pas valides.";
  }
  return "L’action demandée a échoué.";
}

async function apiRequest(url, token, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(apiErrorMessage(body));
  }
  if (response.status === 204) return null;
  return response.json();
}

export default function SettingsPage({
  apiUrl,
  token,
  currentUser,
  onPasswordChanged,
  onThemeChanged,
}) {
  const canManageTeam = ["owner", "admin"].includes(currentUser.role);
  const isOwner = currentUser.role === "owner";
  const [organization, setOrganization] = useState(null);
  const [users, setUsers] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [auditEntries, setAuditEntries] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState("organization");
  const [organizationName, setOrganizationName] = useState("");
  const [newUser, setNewUser] = useState({ email: "", role: "viewer" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });

  async function loadSettings() {
    try {
      const requests = [apiRequest(`${apiUrl}/api/v1/organization`, token)];
      if (canManageTeam) {
        requests.push(apiRequest(`${apiUrl}/api/v1/users`, token));
        requests.push(apiRequest(`${apiUrl}/api/v1/invitations`, token));
        requests.push(apiRequest(`${apiUrl}/api/v1/audit-entries?limit=100`, token));
      }
      const [organizationData, userData = [], invitationData = [], auditData = []] = await Promise.all(requests);
      setOrganization(organizationData);
      setOrganizationName(organizationData.name);
      setUsers(userData);
      setInvitations(invitationData);
      setAuditEntries(auditData);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  useEffect(() => {
    loadSettings();
  }, [apiUrl, token, canManageTeam]);

  async function saveOrganization(event) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const updated = await apiRequest(`${apiUrl}/api/v1/organization`, token, {
        method: "PATCH",
        body: JSON.stringify({ name: organizationName }),
      });
      setOrganization(updated);
      setMessage("Le nom de la PME a été mis à jour.");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function createUser(event) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const invitation = await apiRequest(`${apiUrl}/api/v1/invitations`, token, {
        method: "POST",
        body: JSON.stringify(newUser),
      });
      setNewUser({ email: "", role: "viewer" });
      setMessage(
        invitation.email_sent
          ? "Invitation envoyée. Le lien personnel expirera dans 24 heures."
          : "Invitation créée, mais l’e-mail n’a pas pu être remis. Vérifiez la configuration SMTP.",
      );
      await loadSettings();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function updateUser(user, changes) {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await apiRequest(`${apiUrl}/api/v1/users/${user.id}`, token, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      setMessage("Les droits du compte ont été mis à jour.");
      await loadSettings();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(event) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await apiRequest(`${apiUrl}/api/v1/auth/change-password`, token, {
        method: "POST",
        body: JSON.stringify(passwords),
      });
      onPasswordChanged();
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
    }
  }

  async function updateTheme(theme) {
    if (theme === currentUser.theme || busy) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const updatedUser = await apiRequest(`${apiUrl}/api/v1/auth/preferences`, token, {
        method: "PATCH",
        body: JSON.stringify({ theme }),
      });
      onThemeChanged(updatedUser);
      setMessage(`Le thème « ${themeOptions.find((option) => option.id === theme)?.name} » est maintenant actif.`);
      if (canManageTeam) await loadSettings();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function canEditUser(user) {
    if (user.id === currentUser.id || user.role === "owner") return false;
    if (currentUser.role === "admin" && user.role === "admin") return false;
    return canManageTeam;
  }

  const pendingInvitations = invitations.filter((invitation) => invitation.status === "pending");
  const activeTheme = themeOptions.find((option) => option.id === currentUser.theme) || themeOptions[1];
  const tabs = [
    { id: "organization", label: "Organisation", meta: organization?.name || "Votre PME" },
    ...(canManageTeam ? [{ id: "team", label: "Équipe", meta: `${users.length} compte${users.length > 1 ? "s" : ""}` }] : []),
    { id: "security", label: "Sécurité", meta: "Mot de passe" },
    { id: "appearance", label: "Apparence", meta: activeTheme.name },
    ...(canManageTeam ? [{ id: "audit", label: "Journal", meta: `${auditEntries.length} action${auditEntries.length > 1 ? "s" : ""}` }] : []),
  ];

  return (
    <section className="page-section settings-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">ESPACE PME</p>
          <h2>Centre de configuration</h2>
          <p>Gérez votre organisation, votre équipe, la sécurité et l’apparence depuis un seul tableau de bord.</p>
        </div>
      </div>

      {message && <p className="settings-feedback success" role="status">{message}</p>}
      {error && <p className="settings-feedback failure" role="alert">{error}</p>}

      <nav className="settings-tabs" role="tablist" aria-label="Rubriques des paramètres">
        {tabs.map((tab) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "active" : ""}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
          >
            <span>{tab.label}</span>
            <small>{tab.meta}</small>
          </button>
        ))}
      </nav>

      <div className="settings-tab-content" role="tabpanel">
        {activeTab === "organization" && (
          <div className="settings-tab-panel">
            <div className="settings-overview">
              <article>
                <span>Organisation</span>
                <strong>{organization?.name || "Chargement…"}</strong>
                <p>Identifiant de connexion : <b>{organization?.slug || "—"}</b></p>
              </article>
              <article>
                <span>Votre compte</span>
                <strong>{currentUser.email}</strong>
                <p>Rôle : <b>{roleLabels[currentUser.role]}</b></p>
              </article>
              <article>
                <span>API utilisée</span>
                <strong>{apiUrl}</strong>
                <p>Les secrets et mots de passe ne sont jamais affichés.</p>
              </article>
            </div>
            {isOwner ? (
              <form className="settings-panel settings-form-narrow" onSubmit={saveOrganization}>
                <div><p className="eyebrow">IDENTITÉ</p><h3>Nom public de la PME</h3></div>
                <p className="panel-description">Ce nom apparaît dans l’espace de travail et dans les futurs rapports commerciaux.</p>
                <label>Nom affiché
                  <input value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} minLength="2" maxLength="120" required />
                </label>
                <button disabled={busy}>Enregistrer les modifications</button>
              </form>
            ) : (
              <article className="settings-info-card">
                <p className="eyebrow">INFORMATION</p>
                <h3>Identité gérée par le propriétaire</h3>
                <p>Votre rôle vous permet de consulter ces informations, mais pas de modifier l’identité de la PME.</p>
              </article>
            )}
          </div>
        )}

        {activeTab === "team" && canManageTeam && (
          <div className="settings-team-dashboard">
            <form className="settings-panel" onSubmit={createUser}>
              <div><p className="eyebrow">NOUVEAU COMPTE</p><h3>Ajouter un collaborateur</h3></div>
              <label>Adresse e-mail
                <input type="email" value={newUser.email} onChange={(event) => setNewUser({ ...newUser, email: event.target.value })} required />
              </label>
              <label>Rôle
                <select value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}>
                  {isOwner && <option value="admin">Administrateur</option>}
                  <option value="analyst">Analyste</option>
                  <option value="viewer">Lecture seule</option>
                </select>
              </label>
              <small>Le collaborateur recevra un lien personnel valable 24 heures pour choisir son mot de passe.</small>
              <button disabled={busy}>Envoyer l’invitation</button>
            </form>

            <section className="team-panel">
              <div className="team-panel-heading">
                <div><p className="eyebrow">ACCÈS</p><h3>Équipe ({users.length})</h3></div>
              </div>
              {pendingInvitations.length > 0 && (
                <div className="pending-invitations">
                  <strong>Invitations en attente</strong>
                  {pendingInvitations.map((invitation) => (
                    <div key={invitation.id}>
                      <span>{invitation.email}</span>
                      <small>{roleLabels[invitation.role]} · expire le {new Date(invitation.expires_at).toLocaleString("fr-FR")}</small>
                    </div>
                  ))}
                </div>
              )}
              <div className="team-list">
                {users.map((user) => {
                  const editable = canEditUser(user);
                  return (
                    <article className={`team-member ${user.is_active ? "" : "disabled"}`} key={user.id}>
                      <div className="team-member-main">
                        <span className="member-avatar">{user.email.slice(0, 2).toUpperCase()}</span>
                        <div><strong>{user.email}</strong><small>{user.is_active ? "Compte actif" : "Compte désactivé"}</small></div>
                      </div>
                      <div className="team-member-actions">
                        <select
                          aria-label={`Rôle de ${user.email}`}
                          value={user.role}
                          disabled={!editable || busy}
                          onChange={(event) => updateUser(user, { role: event.target.value })}
                        >
                          {user.role === "owner" && <option value="owner">Propriétaire</option>}
                          {isOwner && <option value="admin">Administrateur</option>}
                          <option value="analyst">Analyste</option>
                          <option value="viewer">Lecture seule</option>
                        </select>
                        {editable && (
                          <button
                            type="button"
                            className={user.is_active ? "danger-button" : "secondary-button"}
                            disabled={busy}
                            onClick={() => updateUser(user, { is_active: !user.is_active })}
                          >
                            {user.is_active ? "Désactiver" : "Réactiver"}
                          </button>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          </div>
        )}

        {activeTab === "security" && (
          <form className="settings-panel settings-form-narrow" onSubmit={changePassword}>
            <div><p className="eyebrow">SÉCURITÉ DU COMPTE</p><h3>Changer mon mot de passe</h3></div>
            <p className="panel-description">Le changement ferme toutes vos sessions actives afin de protéger immédiatement le compte.</p>
            <label>Mot de passe actuel
              <input type="password" value={passwords.current_password} onChange={(event) => setPasswords({ ...passwords, current_password: event.target.value })} minLength="12" autoComplete="current-password" required />
            </label>
            <label>Nouveau mot de passe
              <input type="password" value={passwords.new_password} onChange={(event) => setPasswords({ ...passwords, new_password: event.target.value })} minLength="12" autoComplete="new-password" required />
            </label>
            <small>12 caractères minimum. Toutes vos sessions seront fermées après modification.</small>
            <button disabled={busy}>Modifier et me reconnecter</button>
          </form>
        )}

        {activeTab === "appearance" && (
          <section className="appearance-panel">
            <div className="appearance-heading">
              <div>
                <p className="eyebrow">PERSONNALISATION</p>
                <h3>Thème de l’interface</h3>
                <p>Le choix est lié à votre compte et vous suivra sur vos autres appareils.</p>
              </div>
              <span>Actuel : {activeTheme.name}</span>
            </div>
            <div className="theme-grid">
              {themeOptions.map((option) => (
                <button
                  type="button"
                  className={`theme-card theme-${option.id} ${currentUser.theme === option.id ? "selected" : ""}`}
                  aria-pressed={currentUser.theme === option.id}
                  disabled={busy}
                  key={option.id}
                  onClick={() => updateTheme(option.id)}
                >
                  <span className="theme-preview" aria-hidden="true">
                    <i />
                    <b><em /><em /><em /></b>
                  </span>
                  <strong>{option.name}</strong>
                  <small>{option.description}</small>
                  <em className="theme-choice">{currentUser.theme === option.id ? "Sélectionné" : "Choisir"}</em>
                </button>
              ))}
            </div>
          </section>
        )}

        {activeTab === "audit" && canManageTeam && (
          <section className="audit-panel settings-audit-panel">
            <div className="audit-panel-heading">
              <div>
                <p className="eyebrow">TRAÇABILITÉ</p>
                <h3>Journal d’audit</h3>
                <p>Historique sécurisé des actions sensibles de cette PME.</p>
              </div>
              <span>{auditEntries.length} événement{auditEntries.length > 1 ? "s" : ""}</span>
            </div>
            <div className="audit-list">
              {auditEntries.length === 0 && (
                <p className="audit-empty">Aucune action n’a encore été enregistrée.</p>
              )}
              {auditEntries.map((entry) => (
                <article className="audit-entry" key={entry.id}>
                  <span className="audit-dot" aria-hidden="true" />
                  <div>
                    <strong>{auditActionLabels[entry.action] || entry.action}</strong>
                    <p>{entry.actor_email} · {roleLabels[entry.actor_role] || entry.actor_role}</p>
                  </div>
                  <div className="audit-target">
                    <span>{auditTarget(entry)}</span>
                    <time dateTime={entry.created_at}>
                      {new Date(entry.created_at).toLocaleString("fr-FR")}
                    </time>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </div>
    </section>
  );
}
