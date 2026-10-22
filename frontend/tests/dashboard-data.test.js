import test from 'node:test';
import assert from 'node:assert/strict';
import {fleetStates, latestChecks, lastCompletedScan, openIncidents, resourceRows, timestamp} from '../src/dashboard-data.js';

test('missing metrics are not converted into zero usage',()=>{
  const servers=[{id:'missing',name:'Absent'},{id:'zero',name:'Zero',latest_metric:{cpu_percent:0}},{id:'bad',name:'Bad',latest_metric:{cpu_percent:'40'}},{id:'real',name:'Real',latest_metric:{cpu_percent:45}}];
  assert.deepEqual(resourceRows(servers,'cpu_percent').map(row=>[row.server.id,row.value]),[['real',45],['zero',0]]);
});
test('resource bars stay in range and sort by measured usage',()=>{
  const rows=resourceRows([{name:'A',latest_metric:{disk_percent:101}},{name:'B',latest_metric:{disk_percent:-1}}],'disk_percent');
  assert.deepEqual(rows.map(row=>row.value),[100,0]);
});
test('latest checks are deduplicated by logical target, not API order',()=>{
  const checks=[{name:'A',checked_at:'2026-10-01',status:'failed'},{name:'B',checked_at:'2026-10-04',status:'healthy'},{name:'A',checked_at:'2026-10-05',status:'healthy'}];
  assert.deepEqual(latestChecks(checks,item=>item.name).map(item=>item.status),['healthy','healthy']);
  assert.equal(latestChecks([],item=>item.id).length,0);
});
test('unknown or future states are not displayed as healthy',()=>{
  assert.deepEqual(fleetStates([{status:'online'},{status:'warning'},{status:'critical'},{status:'offline'},{}]),{online:1,warning:1,critical:1,unknown:2});
});
test('resolved incidents are excluded and severity takes precedence over recency',()=>{
  const result=openIncidents([{id:'1',severity:'warning',message:'RAM',created_at:'2026-10-21',status:'active'},{id:'2',severity:'critical',status:'resolved'}],[{id:'3',severity:'critical',title:'IDS',occurred_at:'2026-10-19',status:'acknowledged'},{id:'4',severity:'high',status:'resolved'}]);
  assert.deepEqual(result.map(item=>[item.id,item.severity,item.href]),[['ids-3','critical','#/ids'],['infra-1','medium','#/alerts']]);
});
test('last completed scan ignores unfinished jobs and uses completion date',()=>{
  assert.equal(lastCompletedScan([{id:1,status:'running'},{id:2,status:'completed',completed_at:'2026-10-20'},{id:3,status:'completed',completed_at:'2026-10-21'}]).id,3);
  assert.equal(lastCompletedScan([]),null);
  assert.equal(timestamp('invalid'),0);
});
