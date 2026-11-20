const form = document.querySelector("form");
const status = document.querySelector("#status");
const graph = document.querySelector("#graph");
const details = document.querySelector("#details");

async function read(path) {
  const response = await fetch(path, {
    headers: {Authorization: "Bearer " + document.querySelector("#token").value},
    redirect: "error",
  });
  if (!response.ok) throw new Error("Request failed (HTTP " + response.status + ")");
  return response.json();
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  graph.replaceChildren();
  details.textContent = "";
  status.textContent = "Loading assessment…";
  const base = "/v1/itag/assessments/" + encodeURIComponent(form.elements.assessment.value);
  try {
    const data = await read(base);
    const violations = new Set(data.explanation.assessment.violating_node_ids);
    const edges = data.graph.edges;
    status.textContent = data.explanation.decision_summary;
    details.textContent = JSON.stringify({
      recorded_pre_sign_facts: data.explanation.recorded_facts,
      model_inference: data.explanation.assessment.semantic,
      temporal: data.explanation.temporal_violations,
      recovery: data.explanation.recovery,
      decision: data.decision,
      latest_outcome: data.latest_outcome,
    }, null, 2);
    for (const node of data.graph.nodes) {
      const card = document.createElement("article");
      card.dataset.trust = node.trust;
      card.classList.toggle("violation", violations.has(node.node_id));
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = (violations.has(node.node_id) ? "Violation · " : "") +
        node.kind + " · " + node.trust;
      button.addEventListener("click", async () => {
        try {
          details.textContent = JSON.stringify(
            await read(base + "/nodes/" + encodeURIComponent(node.node_id)), null, 2
          );
        } catch (error) {
          details.textContent = error.message;
        }
      });
      const id = document.createElement("code");
      id.textContent = node.node_id;
      card.append(button, id);
      for (const edge of edges.filter(item => item.source === node.node_id)) {
        const relation = document.createElement("small");
        relation.textContent = edge.kind + " → " + edge.target + " · " + edge.provenance;
        relation.classList.toggle("inferred", edge.provenance === "MODEL_INFERENCE");
        relation.classList.toggle("violation",
          data.explanation.assessment.violating_edge_ids.includes(edge.edge_id));
        card.append(relation);
      }
      graph.append(card);
    }
  } catch (error) {
    status.textContent = error.message;
  }
});
