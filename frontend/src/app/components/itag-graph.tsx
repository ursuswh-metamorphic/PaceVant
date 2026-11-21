import {useEffect, useMemo, useRef, useState, type CSSProperties} from 'react';
import {Background, Controls, MarkerType, ReactFlow} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {graphRecords} from '@/lib/security-evidence';
import {object, text} from '@/lib/format';
import type {Evidence} from '@/lib/types';
import type {Language} from '@/lib/i18n';
import {PublicRecord} from './security-evidence';

const trusts: Record<string, {color: string; bg: string; labels: [string, string]}> = {
  AUTHENTICATED: {color: '#06705d', bg: '#effaf6', labels: ['Đã xác thực', 'Authenticated']},
  VERIFIED_RECORD: {color: '#2154aa', bg: '#edf4ff', labels: ['Bản ghi đã xác minh', 'Verified record']},
  MODEL_JUDGMENT: {color: '#7950a8', bg: '#f7f1ff', labels: ['Suy luận mô hình', 'Model inference']},
};
const untrusted = {color: '#8f5507', bg: '#fff8ed', labels: ['Chưa được xác minh', 'Unverified']};
const relationships: Record<string, [string, string]> = {
  AUTHORIZES: ['Cấp quyền', 'Authorizes'], CONTRIBUTES_TO: ['Đóng góp vào', 'Contributes to'],
  DEPENDS_ON: ['Phụ thuộc', 'Depends on'], DERIVED_FROM: ['Dẫn xuất từ', 'Derived from'],
  EVALUATED_BY: ['Được đánh giá bởi', 'Evaluated by'], EXECUTED_AS: ['Thực thi thành', 'Executed as'],
  PRECEDES: ['Diễn ra trước', 'Precedes'], PRODUCED_OUTCOME: ['Tạo kết quả', 'Produced outcome'],
  UPDATED_STATE: ['Cập nhật trạng thái', 'Updated state'],
};
export function ItagGraph({graph, language, candidateId}: {graph: Evidence; language: Language; candidateId?: string}) {
  const vi = language === 'vi';
  const viewport = useRef<HTMLDivElement>(null);
  const fit = useRef<(() => void) | null>(null);
  const [selected, setSelected] = useState('');
  useEffect(() => {
    if (!viewport.current) return;
    const observer = new ResizeObserver(() => fit.current?.());
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  const records = useMemo(() => graphRecords(graph), [graph]);
  const nodes = useMemo(() => {
    const candidates = records.nodes.filter(record => record.kind === 'AGENT_ACTION' && record.trust !== 'VERIFIED_RECORD' && object(object(record.data).proposal).intent_id === record.node_id);
    const currentId = candidateId || (candidates.length === 1 ? text(candidates[0].node_id) : undefined);
    const group = (record: Evidence) => record.kind === 'AUTHENTICATED_USER_INTENT' || record.kind === 'MANDATE' ? 0
      : record.kind === 'AGENT_ACTION' || record.kind === 'TRANSACTION_OUTCOME' ? 1
        : ['TOOL_OUTPUT', 'TOOL_OBSERVATION', 'EVIDENCE', 'PORTFOLIO_STATE'].includes(text(record.kind)) ? 2 : 3;
    const counts = [0, 0, 0, 0];
    records.nodes.forEach(record => counts[group(record)]++);
    const offsets = [0];
    for (let i = 1; i < 4; i++) offsets[i] = offsets[i - 1] + Math.max(1, Math.ceil(counts[i - 1] / 6)) * 230 + 90;
    const columns = [0, 0, 0, 0];
    return records.nodes.map(record => {
      const data = object(record.data);
      const candidate = record.node_id === currentId;
      const column = group(record), position = columns[column]++;
      const trust = trusts[text(record.trust)] ?? untrusted;
      return {id: text(record.node_id), position: {x: offsets[column] + Math.floor(position / 6) * 230, y: (position % 6) * 140},
        data: {label: <><strong>{candidate ? (vi ? 'Đề xuất hiện tại' : 'Current candidate') : text(record.kind).replaceAll('_', ' ')}</strong><br/>{trust.labels[vi ? 0 : 1]}<br/>{text(data.state, text(record.node_id).slice(0, 24))}</>},
        selected: selected === record.node_id,
        style: {borderColor: candidate ? '#c0263a' : trust.color, background: trust.bg, boxShadow: selected === record.node_id ? '0 0 0 3px #93b8ff' : undefined}};
    });
  }, [records, candidateId, vi, selected]);
  const edges = useMemo(() => records.edges.map((edge, i) => ({id: text(edge.edge_id, String(i)), source: text(edge.source), target: text(edge.target), label: relationships[text(edge.kind)]?.[vi ? 0 : 1] ?? text(edge.kind), markerEnd: {type: MarkerType.ArrowClosed}, style: {stroke: '#637b9f'}, labelStyle: {fontSize: 10, fill: '#33476b'}, labelBgPadding: [3, 3] as [number, number]})), [records, vi]);
  const picked = records.nodes.find(node => node.node_id === selected);
  if (!nodes.length) return <p>{vi ? 'Chưa có đồ thị nguồn; không tạo thêm nút lịch sử.' : 'No source graph; no history nodes are invented.'}</p>;
  return <div className="itag-explorer">
    <p className="module-note">{vi ? 'Ý định đã xác thực → Hành động và lịch sử → Bằng chứng và nguồn gốc → Đánh giá. Chọn nút để xem nguồn. Chỉ dùng các nút và cạnh đã ghi nhận.' : 'Authenticated intent → Action and history → Evidence and provenance → Assessment. Select a node to inspect its source. Only recorded nodes and edges are shown.'}</p>
    <div className="itag-legend">{[...Object.entries(trusts), ['UNVERIFIED', untrusted] as const].map(([id, trust]) => <span key={id} style={{'--trust-color': trust.color} as CSSProperties}>{trust.labels[vi ? 0 : 1]}</span>)}<span style={{'--trust-color': '#c0263a'} as CSSProperties}>{vi ? 'Đề xuất cần kiểm tra' : 'Candidate under review'}</span></div>
    <div ref={viewport} className="itag-visual" aria-label={vi ? 'Đồ thị ITAG tương tác' : 'Interactive ITAG graph'}><ReactFlow nodes={nodes} edges={edges} onInit={instance => {fit.current = () => {void instance.fitView({padding: .15, minZoom: .03});};}} onNodeClick={(_, node) => setSelected(node.id)} onSelectionChange={({nodes: selection}) => {if (selection[0]) setSelected(selection[0].id);}} fitView fitViewOptions={{padding: .15}} minZoom={.03} maxZoom={2} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} proOptions={{hideAttribution: true}}><Background gap={20}/><Controls showInteractive={false}/></ReactFlow></div>
    <details><summary>{vi ? `Chọn bằng bàn phím · ${nodes.length} nút / ${edges.length} cạnh` : `Keyboard selection · ${nodes.length} nodes / ${edges.length} edges`}</summary><div className="itag-node-list">{records.nodes.map(node => <button type="button" key={text(node.node_id)} aria-pressed={selected === node.node_id} onClick={() => setSelected(text(node.node_id))}>{text(node.kind)} · {text(node.node_id)}</button>)}</div></details>
    {!!records.invalidEdges && <p>{vi ? 'Cạnh thiếu nút nguồn không được vẽ: ' : 'Edges with absent endpoints omitted: '}{records.invalidEdges}</p>}
    {picked && <section className="itag-node-evidence" aria-live="polite"><strong>{text(picked.kind)} · {text(picked.trust)}</strong><p className="fact-hash">{text(picked.node_id)}</p><details open><summary>{vi ? 'Bằng chứng và tham chiếu nguồn' : 'Evidence and source references'}</summary><PublicRecord value={picked}/></details></section>}
  </div>;
}
