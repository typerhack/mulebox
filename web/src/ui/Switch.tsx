// A switch (design-system.md, Settings controls): on in the accent, with the knob on the
// right, so the state is never colour alone. The button is the target, 44px on touch; the track
// inside it is the picture (styles/components.css, `.switch`).

interface Props { checked: boolean; onChange: (next: boolean) => void; labelledBy: string; disabled?: boolean }

export const Switch = ({ checked, onChange, labelledBy, disabled }: Props) => (
  <button type="button" role="switch" aria-checked={checked} aria-labelledby={labelledBy} disabled={disabled}
    onClick={() => onChange(!checked)}
    className="inline-grid min-h-6 flex-none place-items-center rounded-full touch:min-h-ctl-touch touch:min-w-ctl-touch">
    <i aria-hidden className="switch" />
  </button>
);
