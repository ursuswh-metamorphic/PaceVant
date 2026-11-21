import {useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent} from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  BaseEdge,
  Handle,
  Position,
  MarkerType,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Activity,
  BadgeCheck,
  Bot,
  Box,
  Boxes,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  Crosshair,
  GitBranch,
  Layers,
  Maximize2,
  Minus,
  Plus,
  ReceiptText,
  ScanLine,
  ShieldCheck,
  Sigma,
  Workflow,
} from 'lucide-react';
import {useReducedMotion} from 'motion/react';
import {StageDetail} from '@/components/stage-detail';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from '@/components/ui/dialog';
import {Button} from '@/components/ui/button';
import {
  workflowNodes as nodes,
  workflowNodeChecks,
  workflowNodeState,
  type ModuleState,
} from '@/lib/workflow-nodes';
import {PHASES, summarizePhase, phaseMembers} from '@/lib/phases';
import {dictionary, type Language} from '@/lib/i18n';
import type {Job} from '@/lib/types';
import {cn} from '@/lib/utils';
import {stateIcons} from './pipeline-icons';

export const nodeState = workflowNodeState;

const icons = [ShieldCheck, Bot, Boxes, Box, Activity, GitBranch, Sigma, ShieldCheck, BadgeCheck, ScanLine, Layers, ReceiptText];

/* ---------------------------------------------------------------------------
 * Phase-aware layout
 * Three phase rows stacked vertically. Within a row nodes run left → right in
 * their real execution order. The layout is computed from the measured canvas
 * width so the graph renders at zoom 1: text never shrinks to fit. If a row
 * cannot hold all of its nodes at the minimum readable width, it continues on
 * a second line inside the same phase (narrow screens only).
 * ------------------------------------------------------------------------- */
const L = {
  pad: 8,
  gutter: 36,
  padRight: 14,
  headerH: 42,
  nodeH: 128,
  padBottom: 12,
  groupGap: 22,
  colGap: 26,
  lineGap: 32,
  minNodeW: 118,
  maxNodeW: 248,
};

interface Placement {x: number; y: number; w: number; line: number; phase: number}
interface GroupBox {x: number; y: number; w: number; h: number}
interface GraphLayout {height: number; nodes: Placement[]; groups: GroupBox[]; gutterX: number}

function computeLayout(width: number): GraphLayout {
  const groupW = Math.max(260, width - 2 * L.pad);
  const innerX = L.pad + L.gutter;
  const innerW = groupW - L.gutter - L.padRight;
  const placements: Placement[] = new Array(nodes.length);
  const groups: GroupBox[] = [];
  let y = L.pad;

  PHASES.forEach((_, phase) => {
    const members = phaseMembers(phase);
    const fit = Math.floor((innerW + L.colGap) / (L.minNodeW + L.colGap));
    // When a phase must wrap, balance its lines (5 → 3 + 2, never 4 + 1).
    const lines = Math.ceil(members.length / Math.max(1, Math.min(members.length, fit)));
    const cols = Math.ceil(members.length / lines);
    const w = Math.min(L.maxNodeW, (innerW - (cols - 1) * L.colGap) / cols);
    members.forEach((index, k) => {
      const line = Math.floor(k / cols);
      placements[index] = {
        x: innerX + (k % cols) * (w + L.colGap),
        y: y + L.headerH + line * (L.nodeH + L.lineGap),
        w,
        line,
        phase,
      };
    });
    const h = L.headerH + lines * L.nodeH + (lines - 1) * L.lineGap + L.padBottom;
    groups.push({x: L.pad, y, w: groupW, h});
    y += h + L.groupGap;
  });

  return {height: y - L.groupGap + L.pad, nodes: placements, groups, gutterX: L.pad + L.gutter / 2};
}

/** Rough width check (13px semibold Inter ≈ 7.2px per glyph) so only nodes whose title wraps give up a subtitle line. */
function titleWraps(label: string, width: number) {
  return label.length * 7.2 > width - 22;
}

/* --------------------------------------------------------------------------- */

type SecurityNodeData = {index: number; state: ModuleState; language: Language; compact: boolean; onOpen: (index: number) => void};
type PhaseRowData = {phase: number; state: ModuleState; language: Language};
type ReturnEdgeData = {midY: number; gutterX: number};

function SecurityGraphNode({data}: NodeProps<Node<SecurityNodeData, 'security'>>) {
  const {index, state, language, compact, onOpen} = data;
  const node = nodes[index];
  const t = dictionary[language];
  const Icon = icons[index];
  const StatusIcon = stateIcons[state];
  const number = String(index + 1).padStart(2, '0');

  return (
    <div
      className={cn('security-node', 'state-' + state, compact && 'is-compact')}
      tabIndex={0}
      role="button"
      aria-label={`${number} ${node.label}: ${t[state]}`}
      data-testid={'node-' + index}
      onKeyDown={(event: KeyboardEvent) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(index);
        }
      }}
    >
      <Handle type="target" position={Position.Left} id="target-left" className="node-handle" isConnectable={false} />
      <Handle type="target" position={Position.Top} id="target-top" className="node-handle" isConnectable={false} />
      <span className="security-node-number" aria-hidden="true">{number}</span>
      <span className="security-node-icon" aria-hidden="true">
        <Icon size={16} strokeWidth={1.9} />
      </span>
      <strong>{node.label}</strong>
      <p>{node.description[language === 'vi' ? 0 : 1]}</p>
      <span className={'chip tone-' + state}>
        <StatusIcon size={11} strokeWidth={2.6} className={state === 'running' ? 'animate-spin' : ''} aria-hidden="true" />
        {t[state]}
      </span>
      <Handle type="source" position={Position.Right} id="source-right" className="node-handle" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} id="source-bottom" className="node-handle" isConnectable={false} />
    </div>
  );
}

function PhaseRowNode({data}: NodeProps<Node<PhaseRowData, 'phaseRow'>>) {
  const {phase, state, language} = data;
  const vi = language === 'vi';
  const t = dictionary[language];
  const copy = PHASES[phase];
  const StatusIcon = stateIcons[state];
  const label =
    state === 'passed' ? (vi ? 'Hoàn thành' : 'Complete') : state === 'idle' ? t.idle : t[state];
  return (
    <div className="phase-row" data-state={state}>
      <div className="phase-row-head">
        <span className="phase-index">{String(phase + 1).padStart(2, '0')}</span>
        <strong>{copy.title[vi ? 0 : 1]}</strong>
        <span className="phase-row-desc">{copy.description[vi ? 0 : 1]}</span>
        <span className="phase-row-side">
          <span className={'chip tone-' + state}>
            <StatusIcon size={11} strokeWidth={2.6} className={state === 'running' ? 'animate-spin' : ''} aria-hidden="true" />
            {label}
          </span>
        </span>
      </div>
    </div>
  );
}

/** Carriage-return edge: leaves the end of a row, runs back along the left gutter, enters the next row's first node. */
function ReturnEdge({id, sourceX, sourceY, targetX, targetY, markerEnd, style, data}: EdgeProps<Edge<ReturnEdgeData, 'return'>>) {
  const {midY, gutterX} = data ?? {midY: (sourceY + targetY) / 2, gutterX: targetX - 18};
  const r = 10;
  const path = [
    `M ${sourceX} ${sourceY}`,
    `L ${sourceX} ${midY - r}`,
    `Q ${sourceX} ${midY} ${sourceX - r} ${midY}`,
    `L ${gutterX + r} ${midY}`,
    `Q ${gutterX} ${midY} ${gutterX} ${midY + r}`,
    `L ${gutterX} ${targetY - r}`,
    `Q ${gutterX} ${targetY} ${gutterX + r} ${targetY}`,
    `L ${targetX} ${targetY}`,
  ].join(' ');
  return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />;
}

const nodeTypes = {security: SecurityGraphNode, phaseRow: PhaseRowNode};
const edgeTypes = {return: ReturnEdge};

const EDGE = {idle: '#c3ccdc', passed: '#5cb48f', running: '#3d5ce8', rejected: '#d9646f'};

function GraphTools({
  job,
  layout,
  language,
  zoomed,
}: {
  job?: Job;
  layout: GraphLayout;
  language: Language;
  zoomed: boolean;
}) {
  const {setViewport, setCenter, getZoom, zoomIn, zoomOut} = useReactFlow();
  const reduced = useReducedMotion();
  const [follow, setFollow] = useState(true);
  const last = useRef('');
  const vi = language === 'vi';

  // Follow the active module when the user has zoomed in; at 1:1 the whole graph is already visible.
  useEffect(() => {
    if (!job || !follow || !zoomed) return;
    const index =
      job.terminal && job.workflow?.outcome
        ? nodes.length - 1
        : nodes.findIndex(node => node.active.includes(job.active_stage ?? ''));
    const key = job.job_id + ':' + job.active_stage + ':' + job.status;
    if (index < 0 || key === last.current) return;
    last.current = key;
    const p = layout.nodes[index];
    void setCenter(p.x + p.w / 2, p.y + L.nodeH / 2, {zoom: getZoom(), duration: reduced ? 0 : 300});
  }, [job?.job_id, job?.active_stage, job?.status, follow, zoomed, layout, reduced, setCenter, getZoom]);

  return (
    <>
      <button
        type="button"
        className="tool-btn"
        aria-pressed={follow}
        title={vi ? 'Khi phóng to, tự di chuyển đến bước đang chạy' : 'When zoomed in, keep the running step in view'}
        onClick={() => {
          last.current = '';
          setFollow(value => !value);
        }}
      >
        <Crosshair size={13} aria-hidden="true" />
        {vi ? 'Theo dõi' : 'Follow'}
      </button>
      <span className="tool-group" role="group" aria-label={vi ? 'Thu phóng' : 'Zoom'}>
        <button type="button" className="tool-btn tool-icon" aria-label={vi ? 'Thu nhỏ' : 'Zoom out'} onClick={() => void zoomOut({duration: reduced ? 0 : 200})}>
          <Minus size={13} aria-hidden="true" />
        </button>
        <button type="button" className="tool-btn tool-icon" aria-label={vi ? 'Phóng to' : 'Zoom in'} onClick={() => void zoomIn({duration: reduced ? 0 : 200})}>
          <Plus size={13} aria-hidden="true" />
        </button>
      </span>
      <button
        type="button"
        className="tool-btn"
        aria-label={vi ? 'Hiển thị toàn bộ ba giai đoạn' : 'Show all three phases'}
        onClick={() => void setViewport({x: 0, y: 0, zoom: 1}, {duration: reduced ? 0 : 280})}
      >
        <Maximize2 size={13} aria-hidden="true" />
        {vi ? 'Vừa khung' : 'Fit'}
      </button>
    </>
  );
}

function runTone(job?: Job): {state: ModuleState; label: [string, string]} {
  if (!job) return {state: 'idle', label: ['Chờ chạy', 'Ready']};
  if (!job.terminal) return {state: 'running', label: ['Đang chạy', 'Running']};
  if (job.status === 'CONFIRMED') return {state: 'passed', label: ['Hoàn tất', 'Completed']};
  if (job.status === 'REJECTED') return {state: 'rejected', label: ['Đã chặn', 'Blocked']};
  if (job.status === 'UNKNOWN' || job.status === 'INTERRUPTED') return {state: 'unknown', label: ['Chưa xác định', 'Unresolved']};
  return {state: 'failed', label: ['Không hoàn tất', 'Not completed']};
}

export function Pipeline(props: {job?: Job; language: Language}) {
  return (
    <ReactFlowProvider>
      <PipelineCanvas {...props} />
    </ReactFlowProvider>
  );
}

function PipelineCanvas({job, language}: {job?: Job; language: Language}) {
  const t = dictionary[language];
  const vi = language === 'vi';
  const reduced = useReducedMotion();
  const [selected, setSelected] = useState<number | null>(null);
  const [width, setWidth] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const measure = () => setWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const layout = useMemo(() => computeLayout(width || 800), [width]);
  const states = useMemo(() => nodes.map((_, index) => nodeState(job, index)), [job]);

  const graphNodes = useMemo<Node[]>(() => {
    const rows: Node[] = layout.groups.map((group, phase) => ({
      id: 'group-phase-' + phase,
      type: 'phaseRow',
      position: {x: group.x, y: group.y},
      width: group.w,
      height: group.h,
      zIndex: -1,
      data: {
        phase,
        language,
        state: summarizePhase(phaseMembers(phase).map(index => states[index]), !!job?.terminal),
      },
      selectable: false,
      draggable: false,
      focusable: false,
    }));
    const modules: Node[] = nodes.map((node, index) => ({
      id: String(index),
      type: 'security',
      position: {x: layout.nodes[index].x, y: layout.nodes[index].y},
      width: layout.nodes[index].w,
      height: L.nodeH,
      data: {index, state: states[index], language, compact: titleWraps(node.label, layout.nodes[index].w), onOpen: setSelected},
      ariaLabel: node.label,
      draggable: false,
      selectable: false,
      focusable: false,
    }));
    return [...rows, ...modules];
  }, [layout, states, language, job?.terminal]);

  // Edges follow the real execution order 0 → 11; ids are unchanged from the previous graph.
  const edges = useMemo<Edge[]>(() => {
    const list: Edge[] = [];
    for (let i = 0; i < nodes.length - 1; i++) {
      const from = layout.nodes[i];
      const to = layout.nodes[i + 1];
      const sameLine = from.phase === to.phase && from.line === to.line;
      const source = states[i];
      const target = states[i + 1];
      const running = target === 'running';
      const color =
        target === 'rejected' || target === 'failed'
          ? EDGE.rejected
          : running
            ? EDGE.running
            : source === 'passed'
              ? EDGE.passed
              : EDGE.idle;
      const midY =
        from.phase === to.phase
          ? from.y + L.nodeH + L.lineGap / 2
          : layout.groups[from.phase].y + layout.groups[from.phase].h + L.groupGap / 2;
      list.push({
        id: `edge-${i}-${i + 1}`,
        source: String(i),
        target: String(i + 1),
        sourceHandle: sameLine ? 'source-right' : 'source-bottom',
        targetHandle: 'target-left',
        type: sameLine ? 'straight' : 'return',
        data: sameLine ? undefined : {midY, gutterX: layout.gutterX},
        animated: running && !reduced,
        selectable: false,
        focusable: false,
        markerEnd: {type: MarkerType.ArrowClosed, width: 14, height: 14, color},
        style: {stroke: color, strokeWidth: sameLine ? 1.75 : 1.6},
      });
    }
    return list;
  }, [layout, states, reduced]);

  const selectedNode = selected !== null ? nodes[selected] : undefined;
  const SelectedIcon = selected !== null ? icons[selected] : Bot;
  const tone = runTone(job);
  const ToneIcon = stateIcons[tone.state];

  return (
    <div className="execution-canvas" data-testid="execution-pipeline">
      <div className="canvas-head">
        <div className="canvas-head-title">
          <span className="panel-head-icon" aria-hidden="true">
            <Workflow size={17} />
          </span>
          <div>
            <h2>{t.graph}</h2>
            <p>
              {vi
                ? 'Chọn một module để xem đầu vào, kết quả và bằng chứng.'
                : 'Select a module to inspect its input, result and evidence.'}
            </p>
          </div>
        </div>
        <div className="canvas-tools">
          <span className={'chip tone-' + tone.state} data-testid="graph-run-state">
            {tone.state === 'running' ? <span className="live-dot" aria-hidden="true" /> : <ToneIcon size={11} strokeWidth={2.6} aria-hidden="true" />}
            {tone.label[vi ? 0 : 1]}
          </span>
          <GraphTools job={job} layout={layout} language={language} zoomed={zoomed} />
        </div>
      </div>

      <div className="flow-viewport" ref={viewportRef} style={{height: layout.height}}>
        {width > 0 && (
          <ReactFlow
            nodes={graphNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultViewport={{x: 0, y: 0, zoom: 1}}
            minZoom={0.6}
            maxZoom={2}
            nodesConnectable={false}
            nodesDraggable={false}
            nodesFocusable={false}
            edgesFocusable={false}
            elementsSelectable={false}
            panOnDrag={zoomed}
            panOnScroll={false}
            zoomOnScroll={false}
            zoomOnDoubleClick={false}
            preventScrolling={false}
            onMoveEnd={(_, viewport) =>
              setZoomed(Math.abs(viewport.zoom - 1) > 0.01 || Math.abs(viewport.x) > 1 || Math.abs(viewport.y) > 1)
            }
            onNodeClick={(_, node) => {
              if (node.type === 'security') setSelected(Number(node.id));
            }}
            proOptions={{hideAttribution: true}}
            aria-label={vi ? 'Sơ đồ ba giai đoạn kiểm tra giao dịch' : 'Three-phase transaction verification graph'}
          >
            <ViewportSync width={width} />
          </ReactFlow>
        )}
      </div>

      <div className="graph-legend" aria-label={vi ? 'Chú thích trạng thái' : 'State legend'}>
        <span><i className="legend-idle" />{t.idle}</span>
        <span><i className="legend-running" />{t.running}</span>
        <span><i className="legend-passed" />{t.passed}</span>
        <span><i className="legend-rejected" />{t.rejected}</span>
        <span><i className="legend-failed" />{t.failed}</span>
        <span><i className="legend-unknown" />{t.unknown}</span>
      </div>

      <Dialog open={selected !== null} onOpenChange={open => !open && setSelected(null)}>
        <DialogContent className="module-sheet">
          {selectedNode && selected !== null && (
            <>
              <div className="module-sheet-heading">
                <span className="module-sheet-icon">
                  <SelectedIcon size={24} />
                </span>
                <div>
                  <DialogTitle>{selectedNode.label}</DialogTitle>
                  <span className={'chip tone-' + nodeState(job, selected)}>
                    {t[nodeState(job, selected)]}
                  </span>
                </div>
              </div>

              <DialogDescription className="module-description">
                {selectedNode.explanation[vi ? 0 : 1]}
              </DialogDescription>

              <div className="module-sequence">
                <Button variant="ghost" size="sm" disabled={selected === 0} onClick={() => setSelected(selected - 1)}>
                  <ChevronLeft size={14} />
                  {vi ? 'Trước' : 'Previous'}
                </Button>
                <span>
                  {String(selected + 1).padStart(2, '0')} / {nodes.length}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={selected === nodes.length - 1}
                  onClick={() => setSelected(selected + 1)}
                >
                  {vi ? 'Tiếp theo' : 'Next'}
                  <ChevronRight size={14} />
                </Button>
              </div>

              <section className="module-guide">
                <h3>{vi ? 'Module này làm gì?' : 'What does this module do?'}</h3>
                <ul>
                  {(workflowNodeChecks[selected === 11 ? 'RECONCILIATION' : selectedNode.events[0]] ?? []).map(check => (
                    <li key={check[1]}>{check[vi ? 0 : 1]}</li>
                  ))}
                </ul>
              </section>

              {!job?.workflow?.timeline.some(
                event =>
                  selectedNode.events.includes(event.stage) ||
                  (selectedNode.events.includes('PROOF') && event.stage === 'PROOF_REJECTION'),
              ) && (
                <div className="module-empty">
                  {nodeState(job, selected) === 'running' ? (
                    <CircleDashed size={15} className="animate-spin" aria-hidden="true" />
                  ) : null}
                  {nodeState(job, selected) === 'running'
                    ? vi
                      ? 'Bước này đang xử lý. Đầu ra sẽ xuất hiện khi backend ghi nhận kết quả.'
                      : 'This step is running. Output will appear when recorded by the backend.'
                    : vi
                      ? 'Chưa có kết quả xử lý tại bước này.'
                      : 'No processing result has been recorded for this step.'}
                  {job?.terminal && selectedNode.active.includes(job.active_stage ?? '') && (
                    <span className="module-stop">
                      {job.reason_code ?? job.workflow?.reason_code ?? t[nodeState(job, selected)]}
                    </span>
                  )}
                </div>
              )}

              <StageDetail job={job} index={selected} events={selectedNode.events} language={language} />
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Keeps the graph at 1:1 whenever the measured width (and therefore the layout) changes. */
function ViewportSync({width}: {width: number}) {
  const {setViewport} = useReactFlow();
  useEffect(() => {
    void setViewport({x: 0, y: 0, zoom: 1});
  }, [width, setViewport]);
  return null;
}
