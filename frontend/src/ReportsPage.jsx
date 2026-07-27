function formatDate(value) {
  return value ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

export default function ReportsPage({ apiUrl, token, scans }) {
  const completed = scans.filter((scan) => scan.status === "completed");
  async function download(scan) {
    const response = await fetch(`${apiUrl}/api/v1/network-scans/${scan.id}/report`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `audit-reseau-${scan.id}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="page-section">
      <div className="page-heading"><div><p className="eyebrow">DOCUMENTATION</p><h2>Rapports de sécurité</h2><p>Retrouvez et téléchargez les rapports des audits réseau terminés.</p></div></div>
      {!completed.length ? <div className="empty"><h3>Aucun rapport disponible</h3><p>Un rapport apparaîtra après le premier audit réseau terminé.</p></div> :
        <div className="report-grid">{completed.map((scan) => (
          <article className="report-card" key={scan.id}>
            <div className="report-icon">PDF</div>
            <div><h3>Audit {scan.target}</h3><p>{formatDate(scan.completed_at)} · {scan.results.length} équipement(s)</p></div>
            <button onClick={() => download(scan)}>Télécharger</button>
          </article>
        ))}</div>}
    </section>
  );
}
