import { useRef, useState } from 'react';
import InterfaceIcon from './InterfaceIcon';

function formatDate(value) {
  return value ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

export default function ReportsPage({ apiUrl, token, scans }) {
  const completed = scans.filter((scan) => scan.status === "completed");
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const pending = useRef(false);
  async function download(scan) {
    if (pending.current) return;
    pending.current = true; setBusy(scan.id); setError('');
    try {
      const response = await fetch(`${apiUrl}/api/v1/network-scans/${scan.id}/report`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Le rapport n’a pas pu être téléchargé. Réessayez dans un instant.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit-reseau-${scan.id}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e.message || 'Téléchargement indisponible.'); }
    finally { pending.current = false; setBusy(''); }
  }
  return (
    <section className="page-section">
      <div className="page-heading"><div><p className="eyebrow">DOCUMENTATION</p><h2>Rapports de sécurité</h2><p>Vos audits terminés, prêts à être consultés et partagés.</p></div><span className="section-count">{completed.length} rapport{completed.length > 1 ? 's' : ''}</span></div>
      {error && <p className="error" role="alert">{error}</p>}
      {!completed.length ? <div className="empty"><InterfaceIcon name="download"/><h3>Votre premier rapport vous attend</h3><p>Lancez un audit autorisé pour retrouver ici son rapport détaillé.</p><a href="#/scanner">Ouvrir le scanner<InterfaceIcon name="arrow"/></a></div> :
        <div className="report-grid">{completed.map((scan) => (
          <article className="report-card" key={scan.id}>
            <div className="report-icon"><InterfaceIcon name="download"/><span>PDF</span></div>
            <div><h3>Audit {scan.target}</h3><p>{formatDate(scan.completed_at)} · {scan.results?.length || 0} équipement(s)</p></div>
            <button onClick={() => download(scan)} disabled={!!busy} aria-busy={busy === scan.id}><InterfaceIcon name={busy === scan.id ? 'refresh' : 'download'} className={busy === scan.id ? 'is-spinning' : ''}/>{busy === scan.id ? 'Préparation…' : 'Télécharger'}</button>
          </article>
        ))}</div>}
    </section>
  );
}
