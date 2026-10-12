'use strict';
function assistantSelection(snapshot, organization, clock=Date.now()){
 const row=snapshot?.assistant;
 if(!row||organization&&row.org!==organization)return {status:'unknown'};
 const checked=Date.parse(row.checked_at),age=clock-checked;
 if(!Number.isFinite(checked)||age>900000||age< -60000)return {status:'expired'};
 return {status:'ready',...row};
}
