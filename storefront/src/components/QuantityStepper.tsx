import { Minus, Plus } from "lucide-react";

type QuantityStepperProps = {
  value: number;
  min: number;
  max: number;
  label: string;
  onChange: (value: number) => void;
};

export function QuantityStepper({ value, min, max, label, onChange }: QuantityStepperProps) {
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button
        type="button"
        onClick={() => onChange(value - 1)}
        disabled={value <= min}
        aria-label="Retirer une unité"
      >
        <Minus size={15} aria-hidden="true" />
      </button>
      <output aria-live="polite">{value}</output>
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        disabled={value >= max}
        aria-label="Ajouter une unité"
      >
        <Plus size={15} aria-hidden="true" />
      </button>
    </div>
  );
}
