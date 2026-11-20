import {api} from "../../api/client.js";

export async function workflowRequest(mandate, goal, scenario) {
  const request = {mandate_id:mandate.mandate_id, goal, ...(scenario ? {scenario} : {})};
  const health = await api("/health");
  if (!health.require_itag) return request;
  const proposal = await api("/v1/agent/propose", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({mandate_id:mandate.mandate_id, goal}),
  });
  if (proposal.token_in.toLowerCase() !== mandate.token_in.toLowerCase()) {
    throw new Error("ITAG_DEMO_REQUIRES_USDC_TO_WAVAX");
  }
  const spec = await api("/v1/itag/intents", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({kind:"ONE_SHOT_SWAP", mandate_id:mandate.mandate_id,
      objective:goal, deadline:Math.min(Math.floor(Date.now()/1000)+1800, mandate.expires_at),
      total_budget:proposal.amount_in_base_units,
      steps:[{step_id:"swap", min_amount:proposal.amount_in_base_units, max_amount:proposal.amount_in_base_units}]}),
  });
  request.temporal_intent = {spec_id:spec.spec_id, revision:spec.revision, step_id:"swap"};
  return request;
}
