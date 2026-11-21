import * as Select from '@radix-ui/react-select';
import {Check, ChevronDown, ShieldAlert, ArrowRight, ScanEye} from 'lucide-react';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from '@/components/ui/dialog';
import type {Language} from '@/lib/i18n';
import type {ScenarioId} from '@/lib/types';

interface AttackPreset {id:string;title:[string,string];description:[string,string];change:[string,string];checks:string[];expected:[string,string]}
const payment:AttackPreset[]=[
 {id:'payment-recipient',title:['Đánh tráo người nhận','Recipient substitution'],description:['Chỉ dẫn độc hại cố đổi địa chỉ nhận USDC đã được duyệt.','A malicious instruction attempts to replace the approved USDC recipient.'],change:['Địa chỉ đã duyệt → địa chỉ ngoài danh sách cho phép','Approved recipient → recipient outside the allowlist'],checks:['Agent & Intent','Shield + ITAG','Owner Policy'],expected:['Đối chiếu người nhận với yêu cầu gốc và danh sách được phép trước khi cấp quyền ký.','Compare the recipient with the original request and allowlist before authorizing signing.']},
 {id:'payment-amount',title:['Nâng số tiền thanh toán','Payment amount inflation'],description:['Nội dung không đáng tin yêu cầu trả nhiều USDC hơn số tiền được cho phép.','Untrusted content requests more USDC than the authorized payment amount.'],change:['Số tiền cố định → số tiền lớn hơn yêu cầu','Fixed authorized amount → a larger payment'],checks:['Agent & Intent','Economic Risk','Z3 & Phi'],expected:['Kiểm tra số tiền chính xác, hạn mức chi tiêu và thay đổi tài sản đo được.','Check the exact amount, spend limits and measured asset changes.']},
 {id:'payment-replay',title:['Phát lại giao dịch đã ký','Signed transaction replay'],description:['Một giao dịch có nonce đã dùng được đưa trở lại để thử thanh toán lần hai.','A previously used nonce is submitted again to attempt a duplicate payment.'],change:['Nonce còn hiệu lực → nonce đã sử dụng','Valid nonce → previously used nonce'],checks:['Attestor','Exact Preflight','Relayer & PolicyVault'],expected:['Kiểm tra lại nonce, trạng thái và hiệu lực chữ ký; không cho phép thanh toán trùng.','Revalidate nonce, state and signature validity to prevent duplicate payment.']},
];
const swap:AttackPreset[]=[
 {id:'swap-slippage',title:['Hạ đầu ra tối thiểu','Minimum output manipulation'],description:['Báo giá độc hại cố nới điều kiện nhận WAVAX để che giấu tổn thất.','A malicious quote attempts to relax minimum WAVAX output and hide loss.'],change:['Đầu ra được bảo vệ → đầu ra dưới giới hạn cho phép','Protected output → output below the allowed bound'],checks:['Trusted Builder','EVM Simulation','Economic Risk','Z3 & Phi'],expected:['Đối chiếu đầu ra mô phỏng với intent, báo giá độc lập và giới hạn tổn thất.','Compare simulated output with intent, independent pricing and loss limits.']},
 {id:'swap-oracle',title:['Dùng dữ liệu giá quá hạn','Stale oracle data'],description:['Nguồn dữ liệu đưa ra giá cũ để định giá sai giao dịch hoán đổi.','A data source provides an outdated price to misvalue the swap.'],change:['Giá trong cửa sổ hợp lệ → giá đã quá hạn','Price within the valid window → expired price data'],checks:['Owner Policy','Economic Risk','Attestor'],expected:['Kiểm tra nguồn giá và cửa sổ hiệu lực, rồi kiểm tra lại trước khi ký.','Verify price provenance and validity, then revalidate before signing.']},
 {id:'swap-route',title:['Thay router ngoài phạm vi','Unauthorized swap router'],description:['Phản hồi công cụ cố chuyển giao dịch sang contract ngoài phạm vi được cấp quyền.','A tool response attempts to route the swap through an unauthorized contract.'],change:['Đường giao dịch được duyệt → router ngoài phạm vi','Approved route → unauthorized router'],checks:['Trusted Builder','Shield + ITAG','Relayer & PolicyVault'],expected:['Ràng buộc contract đích, đường giao dịch và calldata với phạm vi được phép.','Bind target contract, route and calldata to the authorized scope.']},
];
export function presetsFor(scenario:ScenarioId){return scenario==='swap'?swap:payment;}
export function AttackSelect({value,onChange,disabled,language,scenario}:{value:string;onChange:(value:string)=>void;disabled:boolean;language:Language;scenario:ScenarioId}){
 const vi=language==='vi',index=vi?0:1,presets=presetsFor(scenario),selected=presets.find(preset=>preset.id===value);
 return <section className="attack-section">
  <div className="attack-heading"><ShieldAlert size={16}/><h3>{vi?'Kiểm tra bảo mật':'Security check'}</h3><span>{vi?'Tùy chọn':'Optional'}</span></div>
  <Select.Root value={selected?.id??'none'} onValueChange={onChange} disabled={disabled}>
   <Select.Trigger className="attack-trigger" aria-label={vi?'Chọn kịch bản tấn công':'Select attack scenario'}><Select.Value/><Select.Icon><ChevronDown size={16}/></Select.Icon></Select.Trigger>
   <Select.Portal><Select.Content className="attack-menu protocol-attack-menu" position="popper" sideOffset={6} collisionPadding={16}>
    <Select.Viewport><Select.Group><Select.Label className="attack-menu-label">{scenario==='swap'?(vi?'Hoán đổi USDC → WAVAX':'USDC → WAVAX swap'):(vi?'Thanh toán USDC':'USDC payment')}</Select.Label>
     <Select.Item className="attack-option" value="none"><Select.ItemText>{vi?'Không thêm tấn công':'No attack'}</Select.ItemText><Select.ItemIndicator><Check size={15}/></Select.ItemIndicator></Select.Item>
     {presets.map(preset=><Select.Item className="attack-option" key={preset.id} value={preset.id}><Select.ItemText>{preset.title[index]}</Select.ItemText><Select.ItemIndicator><Check size={15}/></Select.ItemIndicator></Select.Item>)}
    </Select.Group></Select.Viewport>
   </Select.Content></Select.Portal>
  </Select.Root>
  {selected&&<div className="attack-selected-note"><span><ScanEye size={13}/>{vi?'Bản xem trước kịch bản':'Scenario preview'}</span><p>{selected.description[index]}</p></div>}
 </section>;
}
export function AttackPreview({scenario,value,open,onOpenChange,language}:{scenario:ScenarioId;value:string;open:boolean;onOpenChange:(open:boolean)=>void;language:Language}){
 const vi=language==='vi',index=vi?0:1,preset=presetsFor(scenario).find(item=>item.id===value);
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="module-sheet attack-preview-sheet">
  <div className="module-sheet-heading"><span className="module-sheet-icon attack-preview-icon"><ShieldAlert size={24}/></span><div><DialogTitle>{preset?.title[index]}</DialogTitle><span className="module-state">{vi?'Bản xem trước':'Preview'}</span></div></div>
  <DialogDescription className="module-description">{preset?.description[index]}</DialogDescription>
  {preset&&<div className="attack-preview-body"><section><h3>{vi?'Giao dịch được chọn':'Selected operation'}</h3><p>{scenario==='swap'?(vi?'Hoán đổi USDC sang WAVAX qua LFJ.':'Swap USDC for WAVAX through LFJ.'):(vi?'Thanh toán USDC đến địa chỉ đã duyệt.':'Pay USDC to the approved recipient.')}</p></section>
   <section><h3>{vi?'Thay đổi mà kẻ tấn công muốn thực hiện':'Attempted manipulation'}</h3><p className="attack-mutation">{preset.change[index]}</p></section>
   <section><h3>{vi?'Các lớp kiểm tra liên quan':'Relevant security checks'}</h3><div className="attack-checkpoints">{preset.checks.map((check,i)=><span key={check}>{i>0&&<ArrowRight size={13}/>}<strong>{check}</strong></span>)}</div></section>
   <section><h3>{vi?'Điều cần được bảo vệ':'Protection objective'}</h3><p>{preset.expected[index]}</p></section>
   <div className="preview-disclosure"><ScanEye size={18}/><p>{vi?'Đây là bản mô tả kịch bản. Chưa có tấn công được thực thi hoặc kết quả kiểm tra được ghi nhận.':'This is a scenario specification. No attack has been executed or verification result recorded.'}</p></div>
  </div>}
 </DialogContent></Dialog>;
}
