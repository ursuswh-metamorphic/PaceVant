import {useState, useMemo, useEffect, useRef} from 'react';
import {ReactFlow, Background, Controls, MiniMap, useNodesInitialized, useReactFlow, Handle, Position, MarkerType, type Node, type NodeProps} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {Check, Circle, CircleAlert, LoaderCircle, Minus, Bot, ShieldCheck, Boxes, Box, Activity, BadgeCheck, ScanLine, Layers, ReceiptText, GitBranch, Sigma, Focus, ChevronLeft, ChevronRight} from 'lucide-react';
import {useReducedMotion} from 'motion/react';
import {StageDetail} from '@/components/stage-detail';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from '@/components/ui/dialog';
import {Button} from '@/components/ui/button';
import {workflowNodes as nodes, workflowNodeChecks, workflowNodeState, type ModuleState} from '@/lib/workflow-nodes';
import {dictionary,type Language} from '@/lib/i18n';
import type {Job} from '@/lib/types';
import {cn} from '@/lib/utils';

export const nodeState=workflowNodeState;
type SecurityNode=Node<{index:number;state:ModuleState;language:Language},'security'>;
const icons=[ShieldCheck,Bot,Boxes,Box,Activity,GitBranch,Sigma,ShieldCheck,BadgeCheck,ScanLine,Layers,ReceiptText];
function SecurityGraphNode({data}:NodeProps<SecurityNode>){
 const {index,state,language}=data,node=nodes[index],t=dictionary[language],Icon=icons[index];
 const StatusIcon=state==='passed'?Check:state==='running'?LoaderCircle:['rejected','failed','unknown'].includes(state)?CircleAlert:state==='skipped'?Minus:Circle;
 return <div className={cn('security-node','state-'+state)}>
  <Handle type="target" position={Position.Left}/>
  <div className="security-node-heading"><span className="security-node-icon"><Icon size={18} strokeWidth={1.75}/></span><span className="security-node-number">{String(index+1).padStart(2,'0')}</span></div>
  <strong>{node.label}</strong><p>{node.description[language==='vi'?0:1]}</p>
  <span className="security-node-status"><StatusIcon size={12} className={state==='running'?'animate-spin':''}/>{t[state]}</span>
  <Handle type="source" position={Position.Right}/>
 </div>;
}
const nodeTypes={security:SecurityGraphNode};
function ViewportNavigation({job,language}:{job?:Job;language:Language}){
 const initialized=useNodesInitialized(),{fitView,setCenter,getZoom}=useReactFlow();
 const reduced=useReducedMotion(),[follow,setFollow]=useState(true),last=useRef(''),[phase,setPhase]=useState(0);
 const vi=language==='vi';
 useEffect(()=>{if(!initialized)return;const ids=window.innerWidth<768?['0']:['0','1','2'];void fitView({nodes:ids.map(id=>({id})),padding:.16,minZoom:.6,maxZoom:1,duration:0});},[initialized,fitView]);
 useEffect(()=>{
  if(!initialized||!job||!follow)return;
  const index=job.terminal&&job.workflow?.outcome?nodes.length-1:nodes.findIndex(node=>node.active.includes(job.active_stage??''));
  const key=job.job_id+':'+job.active_stage+':'+job.status;
  if(index<0||key===last.current)return;
  last.current=key;setPhase(nodes[index].phase);
  void setCenter(index*246+102,80,{zoom:Math.max(.75,getZoom()),duration:reduced?0:250});
 },[initialized,job?.job_id,job?.active_stage,job?.status,follow,getZoom,setCenter,reduced]);
 function focusPhase(value:number){setFollow(false);setPhase(value);const first=nodes.findIndex(node=>node.phase===value);void setCenter(first*246+300,80,{zoom:.85,duration:reduced?0:250});}
 return <div className="graph-navigation">
  <div className="graph-phases" role="group" aria-label={vi?'Các giai đoạn xử lý':'Workflow phases'}>{(vi?['Chuẩn bị','Xác minh','Thực thi']:['Prepare','Verify','Execute']).map((label,index)=><Button key={label} variant="ghost" size="sm" aria-pressed={phase===index} onClick={()=>focusPhase(index)}>{label}</Button>)}</div>
  <Button variant="ghost" size="sm" aria-pressed={follow} onClick={()=>{last.current='';setFollow(value=>!value);}} className="graph-follow"><Focus size={14}/>{vi?'Theo dõi':'Follow'}</Button>
 </div>;
}
export function Pipeline({job,language}:{job?:Job;language:Language}){
 const t=dictionary[language],vi=language==='vi',reduced=useReducedMotion(),[selected,setSelected]=useState<number|null>(null);
 const graphNodes=useMemo<SecurityNode[]>(()=>nodes.map((node,index)=>({id:String(index),type:'security',width:204,height:160,position:{x:index*246,y:0},data:{index,state:nodeState(job,index),language},ariaLabel:node.label,draggable:false})),[job,language]);
 const edges=useMemo(()=>nodes.slice(1).map((_,i)=>({id:'edge-'+i,source:String(i),target:String(i+1),type:'default',animated:!reduced&&nodeState(job,i+1)==='running',markerEnd:{type:MarkerType.ArrowClosed,width:16,height:16},style:{stroke:nodeState(job,i)==='passed'?'#85bca4':'#bfcbdc',strokeWidth:1.5}})),[job,reduced]);
 const selectedNode=selected!==null?nodes[selected]:undefined,SelectedIcon=selected!==null?icons[selected]:Bot;
 return <div className="execution-canvas" data-testid="execution-pipeline">
  <div className="canvas-title"><h3>{t.graph}</h3><span>{vi?'Chọn một module để xem chức năng và dữ liệu xử lý':'Select a module to explore its role and evidence'}</span></div>
  <div className="flow-viewport linear-flow"><ReactFlow nodes={graphNodes} edges={edges} nodeTypes={nodeTypes} minZoom={.15} maxZoom={1.4} nodesConnectable={false} onNodeClick={(_,node)=>setSelected(Number(node.id))} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){const id=(event.target as HTMLElement).closest('.react-flow__node')?.getAttribute('data-id');if(id){event.preventDefault();setSelected(Number(id));}}}} proOptions={{hideAttribution:true}}>
   <ViewportNavigation job={job} language={language}/><Background gap={22} size={1} color="#dce3ee"/><Controls showInteractive={false}/><MiniMap pannable zoomable nodeColor={node=>node.data.state==='passed'?'#80bda0':node.data.state==='running'?'#6485d8':'#c5d0e1'} ariaLabel={vi?'Sơ đồ toàn bộ quy trình':'Full workflow map'}/>
  </ReactFlow></div>
  <div className="graph-legend"><span><i className="legend-idle"/>{t.idle}</span><span><i className="legend-running"/>{t.running}</span><span><i className="legend-passed"/>{t.passed}</span><span><i className="legend-rejected"/>{t.rejected}</span></div>
  <Dialog open={selected!==null} onOpenChange={open=>{if(!open)setSelected(null);}}><DialogContent className="module-sheet">
   {selectedNode&&selected!==null&&<>
    <div className="module-sheet-heading"><span className="module-sheet-icon"><SelectedIcon size={24}/></span><div><DialogTitle>{selectedNode.label}</DialogTitle><span className={'module-state state-'+nodeState(job,selected)}>{t[nodeState(job,selected)]}</span></div></div>
    <DialogDescription className="module-description">{selectedNode.explanation[vi?0:1]}</DialogDescription>
    <div className="module-sequence"><Button variant="ghost" size="sm" disabled={selected===0} onClick={()=>setSelected(selected-1)}><ChevronLeft size={14}/>{vi?'Trước':'Previous'}</Button><span>{String(selected+1).padStart(2,'0')} / {nodes.length}</span><Button variant="ghost" size="sm" disabled={selected===nodes.length-1} onClick={()=>setSelected(selected+1)}>{vi?'Tiếp theo':'Next'}<ChevronRight size={14}/></Button></div>
    <section className="module-guide"><h3>{vi?'Module này làm gì?':'What does this module do?'}</h3><ul>{(workflowNodeChecks[selected===11?'RECONCILIATION':selectedNode.events[0]]??[]).map(check=><li key={check[1]}>{check[vi?0:1]}</li>)}</ul></section>
    {!job?.workflow?.timeline.some(event=>selectedNode.events.includes(event.stage)||(selectedNode.events.includes('PROOF')&&event.stage==='PROOF_REJECTION'))&&<p className="module-empty">{nodeState(job,selected)==='running'?(vi?'Bước này đang xử lý. Đầu ra sẽ xuất hiện khi backend ghi nhận kết quả.':'This step is running. Output will appear when recorded by the backend.'):(vi?'Chưa có kết quả xử lý tại bước này.':'No processing result has been recorded for this step.')}{job?.terminal&&selectedNode.active.includes(job.active_stage??'')&&<span className="module-stop">{job.reason_code??job.workflow?.reason_code??t[nodeState(job,selected)]}</span>}</p>}
    <StageDetail job={job} index={selected} events={selectedNode.events} language={language}/>
   </>}
  </DialogContent></Dialog>
 </div>;
}
