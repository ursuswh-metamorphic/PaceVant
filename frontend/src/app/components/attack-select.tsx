import * as Select from '@radix-ui/react-select';
import {Check, ChevronDown, ShieldAlert, ScanEye} from 'lucide-react';
import type {Language} from '@/lib/i18n';
import type {ScenarioId} from '@/lib/types';

interface AttackPreset {
  id: string;
  title: [string, string];
  description: [string, string];
  change: [string, string];
  checks: string[];
  expected: [string, string];
}

const payment: AttackPreset[] = [
  {
    id: 'payment-amount',
    title: ['Nâng số tiền thanh toán', 'Payment amount inflation'],
    description: [
      'Nội dung không đáng tin yêu cầu trả nhiều USDC hơn số tiền được cho phép.',
      'Increase the payment from 0.01 to 0.02 USDC with the original signature; the contract must reject the changed data.',
    ],
    change: [
      'Số tiền cố định → số tiền lớn hơn yêu cầu',
      'Fixed authorized amount → larger payment amount',
    ],
    checks: ['Agent & Intent', 'Economic Risk', 'Z3 & Phi'],
    expected: [
      'Kiểm tra số tiền chính xác, hạn mức chi tiêu và thay đổi tài sản đo được.',
      'Check exact amount, spend limits and measured asset changes.',
    ],
  },
  {
    id: 'payment-replay',
    title: ['Phát lại giao dịch đã ký', 'Signed transaction replay'],
    description: [
      'Một giao dịch có nonce đã dùng được đưa trở lại để thử thanh toán lần hai.',
      'A previously used nonce is submitted again to attempt duplicate payment.',
    ],
    change: [
      'Nonce còn hiệu lực → nonce đã sử dụng',
      'Valid nonce → previously used nonce',
    ],
    checks: ['Attestor', 'Exact Preflight', 'Relayer & PolicyVault'],
    expected: [
      'Kiểm tra lại nonce, trạng thái và hiệu lực chữ ký; không cho phép thanh toán trùng.',
      'Revalidate nonce, state and signature validity to prevent duplicate payment.',
    ],
  },
];

const swap: AttackPreset[] = [
  {
    id: 'swap-slippage',
    title: ['Hạ đầu ra tối thiểu', 'Minimum output manipulation'],
    description: [
      'Báo giá độc hại cố nới điều kiện nhận WAVAX để che giấu tổn thất.',
      'Lower minimum WAVAX output to 1 base unit with the original signature; the contract must reject it.',
    ],
    change: [
      'Đầu ra được bảo vệ → đầu ra dưới giới hạn cho phép',
      'Protected output → output below the allowed bound',
    ],
    checks: ['Trusted Builder', 'EVM Simulation', 'Economic Risk', 'Z3 & Phi'],
    expected: [
      'Đối chiếu đầu ra mô phỏng với intent, báo giá độc lập và giới hạn tổn thất.',
      'Compare simulated output with intent, independent pricing and loss limits.',
    ],
  },
  {
    id: 'swap-route',
    title: ['Thay router ngoài phạm vi', 'Unauthorized swap router'],
    description: [
      'Phản hồi công cụ cố chuyển giao dịch sang contract ngoài phạm vi được cấp quyền.',
      'Replace the swap target with an unapproved router while retaining the original signature; the contract must reject it.',
    ],
    change: [
      'Đường giao dịch được duyệt → router ngoài phạm vi',
      'Approved route → unauthorized router',
    ],
    checks: ['Trusted Builder', 'Shield + ITAG', 'Relayer & PolicyVault'],
    expected: [
      'Ràng buộc contract đích, đường giao dịch và calldata với phạm vi được phép.',
      'Bind target contract, route and calldata to the authorized scope.',
    ],
  },
];

export function presetsFor(scenario: ScenarioId) {
  return scenario === 'swap' ? swap : payment;
}

export function AttackSelect({
  value,
  onChange,
  disabled,
  language,
  scenario,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  language: Language;
  scenario: ScenarioId;
}) {
  const vi = language === 'vi';
  const index = vi ? 0 : 1;
  const presets = presetsFor(scenario);
  const selected = presets.find(preset => preset.id === value);

  return (
    <section className="attack-section">
      <div className="attack-heading">
        <ShieldAlert size={15} />
        <h3>{vi ? 'Kiểm tra bảo mật' : 'Security check'}</h3>
        <span>{vi ? 'Tùy chọn' : 'Optional'}</span>
      </div>

      <Select.Root value={selected?.id ?? 'none'} onValueChange={onChange} disabled={disabled}>
        <Select.Trigger
          className="attack-trigger"
          aria-label={vi ? 'Chọn kịch bản tấn công' : 'Select attack scenario'}
        >
          <Select.Value />
          <Select.Icon>
            <ChevronDown size={15} className="text-slate-400" />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Content
            className="protocol-attack-menu"
            position="popper"
            sideOffset={6}
            collisionPadding={16}
          >
            <Select.Viewport>
              <Select.Group>
                <Select.Label className="attack-menu-label">
                  {scenario === 'swap'
                    ? vi
                      ? 'Hoán đổi USDC → WAVAX'
                      : 'USDC → WAVAX swap'
                    : vi
                      ? 'Thanh toán USDC'
                      : 'USDC payment'}
                </Select.Label>
                <Select.Item className="attack-option" value="none">
                  <Select.ItemText>{vi ? 'Không thêm tấn công' : 'Standard transaction'}</Select.ItemText>
                  <Select.ItemIndicator>
                    <Check size={14} className="text-primary" />
                  </Select.ItemIndicator>
                </Select.Item>
                {presets.map(preset => (
                  <Select.Item className="attack-option" key={preset.id} value={preset.id}>
                    <Select.ItemText>{preset.title[index]}</Select.ItemText>
                    <Select.ItemIndicator>
                      <Check size={14} className="text-primary" />
                    </Select.ItemIndicator>
                  </Select.Item>
                ))}
              </Select.Group>
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {selected && (
        <div className="attack-selected-note">
          <span>
            <ScanEye size={13} />
            {vi ? 'Mục tiêu kiểm tra bảo mật' : 'Target security condition'}
          </span>
          <p>{selected.description[index]}</p>
        </div>
      )}
    </section>
  );
}
