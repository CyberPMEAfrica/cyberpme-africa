function formatDate(value) {
  return value ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

export default function ReportsPage({ apiUrl, scans }) {
  const completed = scans.filter((scan) => scan.status === "completed");
  return (
    <section className="page-section">
      <div className="page-heading"><div><p className="eyebrow">DOCUMENTATION</p><h2>Rapports de sécurité</h2><p>Retrouvez et téléchargez les rapports des audits réseau terminés.</p></div></div>
      {!completed.length ? <div className="empty"><h3>Aucun rapport disponible</h3><p>Un rapport apparaîtra après le premier audit réseau terminé.</p></div> :
        <div className="report-grid">{completed.map((scan) => (
          <article className="report-card" key={scan.id}>
            <div className="report-icon">PDF</div>
            <div><h3>Audit {scan.target}</h3><p>{formatDate(scan.completed_at)} · {scan.results.length} équipement(s)</p></div>
            <a href={`${apiUrl}/api/v1/network-scans/${scan.id}/report`}>Télécharger</a>
          </article>
        ))}</div>}
    </section>
  );
}
