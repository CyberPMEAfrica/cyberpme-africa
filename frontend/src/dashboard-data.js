export const stateLabels = { online: 'Opérationnel', warning: 'Attention', critical: 'Critique', unknown: 'En attente' };
export const severityLabels = { critical: 'Critiques', high: 'Élevées', medium: 'Modérées', low: 'Faibles' };
const rank = { critical: 0, high: 1, medium: 2, low: 3 };

export function timestamp(value) {
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}

export function latestChecks(items, key) {
  const latest = new Map();
  for (const item of items) {
    const id = key(item), previous = latest.get(id);
    if (!previous || timestamp(item.checked_at) > timestamp(previous.checked_at)) latest.set(id, item);
  }
  return [...latest.values()];
}

export function resourceRows(servers, field) {
  return servers.flatMap(server => {
    const value = server.latest_metric?.[field];
    return Number.isFinite(value) ? [{ server, value: Math.max(0, Math.min(100, value)) }] : [];
  }).sort((a, b) => b.value - a.value || a.server.name.localeCompare(b.server.name, 'fr'));
}

export function fleetStates(servers) {
  const counts = { online: 0, warning: 0, critical: 0, unknown: 0 };
  for (const server of servers) counts[Object.hasOwn(counts, server.status) ? server.status : 'unknown']++;
  return counts;
}

export function openIncidents(alerts, events) {
  const open = item => !['resolved', 'closed'].includes(item.status);
  return [
    ...alerts.filter(open).map(item => ({ id: `infra-${item.id}`, title: item.message, server: item.server_name, severity: item.severity === 'warning' ? 'medium' : item.severity, date: item.created_at, source: 'Infrastructure', href: '#/alerts' })),
    ...events.filter(open).map(item => ({ id: `ids-${item.id}`, title: item.title, server: item.server_name, severity: item.severity, date: item.occurred_at, source: 'IDS / IPS', href: '#/ids' })),
  ].map(item => ({...item, severity: Object.hasOwn(rank, item.severity) ? item.severity : 'low'}))
    .sort((a, b) => rank[a.severity] - rank[b.severity] || timestamp(b.date) - timestamp(a.date));
}

export function lastCompletedScan(scans) {
  return scans.filter(scan => scan.status === 'completed').sort((a, b) => timestamp(b.completed_at) - timestamp(a.completed_at))[0] || null;
}
